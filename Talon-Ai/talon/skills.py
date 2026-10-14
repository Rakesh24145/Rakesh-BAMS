"""Skill taxonomy, skill extraction, learning catalog, assessment question bank."""
import re

# canonical skill -> words that mean the same thing in a resume
SKILLS = {
    "python": ["python", "python3"],
    "sql": ["sql", "mysql", "postgresql", "postgres", "sql server", "t-sql"],
    "excel": ["excel", "spreadsheets", "google sheets"],
    "power bi": ["power bi", "powerbi"],
    "tableau": ["tableau"],
    "statistics": ["statistics", "statistical analysis", "hypothesis testing"],
    "machine learning": ["machine learning", "scikit-learn", "sklearn"],
    "data visualization": ["data visualization", "data visualisation",
                           "dashboards", "matplotlib"],
    "data cleaning": ["data cleaning", "data cleansing", "data wrangling"],
    "etl": ["etl", "data pipelines", "data pipeline"],
    "pandas": ["pandas"],
    "java": ["java"],
    "javascript": ["javascript", "js", "node.js", "nodejs"],
    "react": ["react", "reactjs"],
    "html css": ["html", "css"],
    "git": ["git", "github", "gitlab"],
    "docker": ["docker", "containers"],
    "kubernetes": ["kubernetes", "k8s"],
    "aws": ["aws", "amazon web services"],
    "azure": ["azure"],
    "linux": ["linux", "bash"],
    "rest apis": ["rest api", "rest apis", "restful", "api development"],
    "communication": ["communication", "stakeholder management",
                      "presentation skills"],
    "project management": ["project management", "pmp"],
    "agile": ["agile", "scrum", "kanban"],
}

# competency framework used by APEX and PRISM
CATEGORY = {
    "python": "Programming", "java": "Programming", "javascript": "Programming",
    "react": "Programming", "html css": "Programming", "rest apis": "Programming",
    "sql": "Data Engineering", "etl": "Data Engineering", "pandas": "Data Engineering",
    "data cleaning": "Data Engineering",
    "excel": "Analytics", "power bi": "Analytics", "tableau": "Analytics",
    "statistics": "Analytics", "machine learning": "Analytics",
    "data visualization": "Analytics",
    "git": "Engineering Practice", "docker": "Engineering Practice",
    "kubernetes": "Engineering Practice", "linux": "Engineering Practice",
    "aws": "Cloud", "azure": "Cloud",
    "communication": "Professional Skills", "project management": "Professional Skills",
    "agile": "Professional Skills",
}


def _pattern(term: str) -> re.Pattern:
    # match the term only as a whole word (so "java" does not match "javascript")
    return re.compile(r"(?<![a-z0-9+#])" + re.escape(term) + r"(?![a-z0-9+#])")


def extract_skills(text: str) -> list:
    low = (text or "").lower()
    found = []
    for skill, words in SKILLS.items():
        if any(_pattern(w).search(low) for w in words):
            found.append(skill)
    return found


def extract_years(text: str) -> int:
    nums = [int(n) for n in re.findall(r"(\d{1,2})\+?\s*(?:years?|yrs?)", (text or "").lower())]
    return max(nums) if nums else 0


# ------------------------- learning catalog (open / free) -------------------
CATALOG = {
    "python": ("Python for Everybody (py4e.com, free)", 20),
    "sql": ("SQLBolt interactive lessons (sqlbolt.com, free)", 8),
    "excel": ("Microsoft Learn: Excel training (free)", 8),
    "power bi": ("Microsoft Learn: Power BI training (free)", 10),
    "tableau": ("Tableau free training videos", 8),
    "statistics": ("Khan Academy: Statistics and Probability (free)", 15),
    "machine learning": ("Google Machine Learning Crash Course (free)", 15),
    "data visualization": ("Kaggle Learn: Data Visualization (free)", 4),
    "data cleaning": ("Kaggle Learn: Data Cleaning (free)", 4),
    "pandas": ("Kaggle Learn: Pandas (free)", 4),
    "git": ("Pro Git book (git-scm.com/book, free)", 6),
    "docker": ("Docker official 'Get started' guide (free)", 6),
    "kubernetes": ("Kubernetes.io interactive tutorials (free)", 10),
    "javascript": ("MDN JavaScript Guide (free)", 15),
    "react": ("react.dev Learn (free)", 12),
    "html css": ("MDN Learn web development (free)", 10),
    "linux": ("Linux Journey (linuxjourney.com, free)", 8),
    "azure": ("Microsoft Learn: Azure Fundamentals path (free)", 10),
    "aws": ("AWS Skill Builder free digital training", 10),
}


def learning_item(skill: str) -> dict:
    title, hours = CATALOG.get(skill, (f"Self-study plan for {skill}", 6))
    return {"skill": skill, "course": title, "hours": hours}


# ------------------------- assessment question bank -------------------------
def _q(qid, text, options, answer):
    return {"id": qid, "q": text, "options": options, "answer": answer}


BANK = {
    "python": [
        _q("py1", "What does len([1, 2, 3]) return?", ["2", "3", "4", "Error"], 1),
        _q("py2", "Which keyword defines a function in Python?",
           ["function", "def", "fn", "define"], 1),
    ],
    "sql": [
        _q("sql1", "Which clause filters rows BEFORE grouping?",
           ["HAVING", "WHERE", "ORDER BY", "LIMIT"], 1),
        _q("sql2", "Which JOIN keeps all rows from the left table?",
           ["INNER JOIN", "LEFT JOIN", "RIGHT JOIN", "CROSS JOIN"], 1),
    ],
    "excel": [
        _q("xl1", "Which function looks up a value in the first column of a range?",
           ["VLOOKUP", "CONCAT", "ROUND", "TRIM"], 0),
        _q("xl2", "What does a PivotTable mainly do?",
           ["Encrypt data", "Summarise data by categories", "Send email", "Draw shapes"], 1),
    ],
    "statistics": [
        _q("st1", "The median of 3, 1, 9, 7, 5 is?", ["3", "5", "7", "9"], 1),
        _q("st2", "A p-value below 0.05 usually means?",
           ["The result is proven true", "The result is unlikely under the null hypothesis",
            "The data is wrong", "The sample is too small"], 1),
    ],
    "machine learning": [
        _q("ml1", "Overfitting means the model...",
           ["Does well on training data but poorly on new data", "Is too simple",
            "Trains too fast", "Has no features"], 0),
        _q("ml2", "Which is a supervised learning task?",
           ["Clustering customers", "Predicting prices from labelled data",
            "Dimensionality reduction", "Grouping anomalies"], 1),
    ],
    "power bi": [
        _q("pb1", "Which language writes measures in Power BI?",
           ["DAX", "HTML", "Java", "Bash"], 0),
        _q("pb2", "Which tool cleans and shapes data before loading?",
           ["Power Query", "Power Automate", "Power Apps", "Azure DevOps"], 0),
    ],
    "data visualization": [
        _q("dv1", "Which chart best shows a trend over time?",
           ["Pie chart", "Line chart", "Word list", "Table of names"], 1),
        _q("dv2", "Which is good dashboard practice?",
           ["Many 3D effects", "Simple layout with clear labels",
            "Hide axis titles", "Random colours"], 1),
    ],
    "data cleaning": [
        _q("dc1", "Missing values are commonly handled by...",
           ["Dropping or imputing with a documented rule", "Ignoring silently",
            "Always converting to 0", "Deleting the file"], 0),
        _q("dc2", "Duplicate customer rows should be...",
           ["Kept always", "Found and removed using a key", "Sorted A-Z",
            "Hidden in charts"], 1),
    ],
    "git": [
        _q("gt1", "Which command records changes into history?",
           ["git commit", "git clone", "git status", "git pull"], 0),
        _q("gt2", "What does git clone do?",
           ["Copies a remote repository locally", "Deletes a branch",
            "Merges two files", "Creates an SSH key"], 0),
    ],
    "communication": [
        _q("cm1", "A stakeholder disagrees with your analysis. Best first step?",
           ["Ignore them", "Listen, clarify concerns, then show evidence",
            "Escalate immediately", "Change the numbers"], 1),
    ],
}

GENERIC = [
    _q("g1", "What is the next number: 2, 4, 8, 16, ?", ["20", "24", "32", "30"], 2),
    _q("g2", "If all A are B and all B are C, then all A are...",
       ["C", "Not C", "Only some C", "Unknown"], 0),
    _q("g3", "Best first step when a task is unclear?",
       ["Guess", "Ask clarifying questions", "Wait silently", "Skip it"], 1),
]
