import spacy
from typing import Dict, List


class TranscriptParser:
    def __init__(self):
        # Load multilingual or French NER model
        try:
            self.nlp = spacy.load("fr_core_news_md")  # better for French
        except:
            self.nlp = spacy.load("en_core_web_md")   # fallback

        # Define lexicons
        self.renovation_types = {
            "bathroom": ["bathroom", "salle de bain", "toilet", "wc"],
            "kitchen": ["kitchen", "cuisine"],
            "living_room": ["living room", "salon"],
            "bedroom": ["bedroom", "chambre"],
            "terrace": ["terrace", "balcony", "balcon"],
            "new_build": ["new build", "construction neuve", "maison neuve"],
            "renovation": ["renovation", "reno", "rénover"]
        }

        self.material_keywords = [
            "tile", "carrelage", "glue", "colle", "paint", "peinture",
            "cement", "ciment", "toilet", "lavabo", "sink", "douche",
            "plomberie", "plaster", "wood", "bois", "parquet",
            "adhesive", "joint", "isolation", "plinth", "flooring", "wall panel"
        ]

        self.vendors = [
            "castorama", "leroy merlin", "manomano", "bricodepot", "mr bricolage"
        ]

    def parse(self, transcript: str) -> Dict:
        doc = self.nlp(transcript.strip().title())

        # Extract region (using NER)
        regions = [ent.text for ent in doc.ents if ent.label_ in ["LOC", "GPE"]]

        # Extract renovation type
        renovation_type = None
        for key, synonyms in self.renovation_types.items():
            for word in synonyms:
                if word.lower() in transcript.lower():
                    renovation_type = key
                    break

        # Extract vendor mentions
        vendor = None
        for v in self.vendors:
            if v.lower() in transcript.lower():
                vendor = v
                break

        # Extract candidate materials
        materials = []
        for chunk in doc.noun_chunks:
            text = chunk.text.lower()
            if any(mat.lower() in text.lower() for mat in self.material_keywords):
                materials.append(chunk.text.strip())

        return {
            "materials": list(set(materials)),
            "region": regions[0] if regions else None,
            "renovation_type": renovation_type,
            "vendor": vendor
        }


# # -------------------- Example --------------------
# if __name__ == "__main__":
#     parser = TranscriptParser()
#     transcript = "Need waterproof glue from Leroy Merlin and 60x60cm matte white wall tiles, better quality this time. For bathroom walls in Paris"
#     result = parser.parse(transcript)
#     print(result)
