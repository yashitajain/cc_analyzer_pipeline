def clean_json(raw_response):
        cleaned = raw_response.strip()
        cleaned = cleaned.replace("```json","").replace("```","")
        cleaned = cleaned.strip()
        return cleaned