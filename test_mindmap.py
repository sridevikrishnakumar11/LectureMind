from models.mindmap_generator import generate_mindmap


keywords = [
    "Artificial Intelligence",
    "Machine Learning",
    "Deep Learning"
]


result = generate_mindmap(keywords)

print(result)