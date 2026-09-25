def generate_mindmap(keywords):

    markdown = "# Lecture Mind Map\n\n"

    for keyword in keywords:
        markdown += f"- {keyword}\n"

    return markdown