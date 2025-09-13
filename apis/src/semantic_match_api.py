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

from sys import path as sys_path
from os import path as os_path

sys_path.append(os_path.realpath('../../'))
sys_path.append(os_path.realpath('../'))
sys_path.append(os_path.realpath('./'))

from utils.operation_utils import read_json
from utils.db_utils import DBUtil



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
app = FastAPI(title="Donizo Semantic Match API")


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

