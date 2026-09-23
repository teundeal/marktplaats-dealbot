import requests

url = "https://api.marktplaats.nl/v2/search"

zoekterm = "camera"

params = {
    "query": zoekterm,
    "offset": 0,
    "limit": 20,
}

body = {
    "query": zoekterm,
    "filters": {
        "price": {
            "to": 5
        },
        "postCode": "3116",
        "distance": 8000
    }
}

response = requests.get(url, params=params, json=body)

print("STATUS:", response.status_code)
print()
print(response.text[:5000])
