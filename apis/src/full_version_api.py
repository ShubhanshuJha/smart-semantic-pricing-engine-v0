"""
Semantic Match API
Provides /material-price endpoint for fuzzy, multilingual contractor queries.
Backed by PostgreSQL + pgvector.
"""

import os
import yaml
import numpy as np
from fastapi import FastAPI, Query
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
import math

from sys import path as sys_path
from os import path as os_path

sys_path.append(os_path.realpath('../../'))
sys_path.append(os_path.realpath('../'))
sys_path.append(os_path.realpath('./'))

from utils.operation_utils import read_json
from utils.db_utils import DBUtil
from pricing_logic.transcript_parser import TranscriptParser
from pricing_logic.labor_calc import parse_transcript, estimate_hours, compute_labor_cost
from pricing_logic.vat_rules import get_vat_rate



# -----------------------------
# Embedding Generator
# -----------------------------
class Embedder:
    def __init__(self, model):
        self.model = model

    def embed(self, data: str) -> List[float]:
        if not data: return []
        vector = self.model.encode(data)
        # Convert to Python list of floats
        return vector.tolist()


# -----------------------------
# Semantic Matcher
# -----------------------------
class SemanticMatcher:
    def __init__(self, config: dict, model):
        self.db_client = DBUtil(db_config=config)
        self.embedder = Embedder(model=model)
    
    def __cosine_similarity(self, vec1, vec2):
        vec1 = np.array(vec1)
        vec2 = np.array(vec2)
        return np.dot(vec1, vec2) / (np.linalg.norm(vec1) * np.linalg.norm(vec2))

    def search(self, query: str, region: Optional[str] = None,
               vendor: Optional[str] = None, limit: int = 5) -> List[dict]:
        vec = self.embedder.embed(query)
        print(f"{query = }")
        rows = []
        try:
            sql = """
            SELECT *,
                1 - (embedding <=> %s::float[]) AS similarity
            FROM Products
            WHERE TRUE
            """
            params = [vec]

            if region:
                sql += " AND region = %s"
                params.append(region)
            if vendor:
                sql += " AND vendor = %s"
                params.append(vendor)

            sql += " ORDER BY similarity DESC LIMIT %s"
            params.append(limit)

            rows = self.db_client.execute_query(query=sql, params=params)
            if not rows:
                raise Exception("Empty rows!")
            print(rows)
        except:
            sql = "SELECT * FROM Products;"
            db_data = self.db_client.execute_query(query=sql)
            scored = []
            rows = []
            for row in db_data:
                emb = row[-1]
                score = self.__cosine_similarity(vec, emb)
                scored.append((score, row))
                row = list(row)
                row.append(score)
                rows.append(row)
            scored.sort(reverse=True, key=lambda x: x[0])  # higher = better
            rows.sort(reverse=True, key=lambda x: x[-1])

        results = []
        for r in rows[:5]:
            similarity = float(r[-1])
            confidence = "high" if similarity > 0.8 else "medium" if similarity > 0.6 else "low"
            # print(confidence)
            r = [val if isinstance(val, str) else str(val or "") for val in r]
            results.append({
                "product_id": r[0],
                "material_name": r[1],
                "description": r[2],
                "unit_price": r[3],
                "unit": r[4],
                "region": r[5],
                "vendor": r[6],
                "vat_rate": r[7],
                "quality_score": r[8],
                "updated_at": r[9],
                "source": r[10],
                "similarity_score": str(round(similarity, 4)),
                "confidence_tier": confidence
            })

        return results

class FeedbackDB:
    def __init__(self, db_client):
        self.db_client = db_client

    def save_feedback(self, data: dict):
        try:
            table_confirmation_query = """
            CREATE TABLE IF NOT EXISTS Feedback (
                id SERIAL PRIMARY KEY,
                task_id VARCHAR(60) NOT NULL,
                quote_id VARCHAR(60) NOT NULL,
                user_type VARCHAR(50) NOT NULL CHECK (user_type IN ('contractor', 'client')),
                verdict VARCHAR(255) NOT NULL,
                comments TEXT,
                created_at TIMESTAMP DEFAULT NOW()
            );
            """
            self.db_client.execute_query(table_confirmation_query)
            insert_query = """
                INSERT INTO Feedback (task_id, quote_id, user_type, verdict, comments, created_at)
            VALUES (%s, %s, %s, %s, %s, NOW())
            """
            params = [
                data.get("task_id"),
                data.get("quote_id"),
                data.get("user_type"),
                data.get("verdict"),
                data.get("comments")
            ]
            self.db_client.execute_query(insert_query, params=params)
            return {"status": "success", "message": "Feedback recorded"}
        except Exception as ex:
            return {"status": "fail", "message": f"Error -- {ex}"}


# -----------------------------
# FastAPI App
# -----------------------------
db_config_path = f"../configs/db_creds.json"
db_config = read_json(path=db_config_path)
print(f"(*) Config: {db_config}")

from sentence_transformers import SentenceTransformer
# lightweight embedding model
model = SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')
matcher = SemanticMatcher(db_config, model=model)
transcript_parser = TranscriptParser()
app = FastAPI(title="Donizo User Exposed API")


class MaterialMatchResponse(BaseModel):
    product_id: str
    material_name: str
    description: str
    unit_price: str
    unit: Optional[str] = None
    region: Optional[str] = None
    vendor: Optional[str] = None
    vat_rate: Optional[str] = None
    updated_at: Optional[str] = None
    source: Optional[str] = None
    similarity_score: float
    confidence_tier: str

class ProposalInvoiceRequest(BaseModel):
    transcript: str

class ProposalInvoiceResponse(BaseModel):
    tasks: list[dict]
    total_estimate: int

class FeedbackRequest(BaseModel):
    task_id: str
    quote_id: str
    user_type: str
    verdict: str
    comment: str

class FeedbackResponse(BaseModel):
    status: str
    message: str


def de_duplicate_products(items: list[dict]):
    seen = set()
    unique_list = []
    for item in items:
        if item["product_id"] not in seen:
            seen.add(item["product_id"])
            unique_list.append(item)
    return unique_list


@app.get("/material-price", response_model=List[MaterialMatchResponse])
def get_material_price(query: str = Query(..., description="Contractor query"),
                       region: Optional[str] = None,
                       vendor: Optional[str] = None,
                       limit: int = 5):
    """
    Semantic material match endpoint.
    Example: /material-price?query=carrelage beige 60x60&region=Île-de-France
    """
    return matcher.search(query, region=region, vendor=vendor, limit=limit)


@app.post("/generate-proposal", response_model=ProposalInvoiceResponse)
def get_proposal(request: ProposalInvoiceRequest):
    result = transcript_parser.parse(request.transcript)
    print(f"{result = }")
    renovation_type = result.get('renovation_type', "Tile bathroom walls")

    final_margin_price = 0
    margin = 10
    total_hours, vat_rate, labor_cost = 0, 0, 0
    pricing_engine_trans = parse_transcript(request.transcript)
    city = pricing_engine_trans["city"] or "Generic"

    for task in pricing_engine_trans["tasks"]:
        tname = task["task_name"]
        hours = estimate_hours(tname, area=task.get("area_m2"))
        labor_cost += compute_labor_cost(hours, city)
        vat_rate = max(vat_rate, get_vat_rate(tname, city))
        total_hours += hours
    prices = []
    for material in result["materials"]:
        query = f"{result.get('vendor')} " + material
        current_price = get_material_price(query=query, region=result.get("region"))[0]
        final_margin_price += (1 + margin) * (1 + float(current_price.get("vat", vat_rate)))
        prices.append(current_price)
    prices = de_duplicate_products(items=prices)
    confidence_score = sum(map(lambda p: float(p["similarity_score"]), prices)) / (len(prices) or 1)

    return {
        "tasks": [
            {
                "label": renovation_type,
                "materials": list(map(lambda p:p["material_name"], prices)),
                "estimated_duration": f"{math.ceil(total_hours / 24)} day",
                "margin_protected_price": final_margin_price,
                "confidence_score": round(confidence_score, 2)
            }
        ],
        "total_estimate": math.ceil(sum(map(lambda p: float(p["unit_price"].replace(".", "").replace(",", ".")), prices)) + final_margin_price + labor_cost)
    }


@app.post("/feedback", response_model=FeedbackResponse)
def post_feedback(feedback: FeedbackRequest):
    feedback_db = FeedbackDB(matcher.db_client)  # reuse DB client
    result = feedback_db.save_feedback(feedback.dict())
    return result

