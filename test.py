from serpapi import GoogleSearch

params = {
  "q": "who is the president of India",
  "api_key": "your_serpapi_key_here",
}

search = GoogleSearch(params)
results = search.get_dict()

print(results.get("answer_box", {}))
