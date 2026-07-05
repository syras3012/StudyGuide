import sys
import logging
from mcp.server.fastmcp import FastMCP

# Setup logging to stderr to prevent stdio corruption
logging.basicConfig(level=logging.INFO, stream=sys.stderr)

mcp = FastMCP("StudyGuide Helper Server")

# Simulated study notes database
STUDY_NOTES = {
    "photosynthesis": (
        "Photosynthesis is the process used by plants, algae and certain bacteria to harness energy from sunlight "
        "and turn it into chemical energy. Key Equation: 6CO2 + 6H2O + light energy -> C6H12O6 + 6O2. "
        "It happens in two stages: Light-dependent reactions (takes place in thylakoid membranes, produces ATP & NADPH) "
        "and Light-independent reactions / Calvin Cycle (takes place in stroma, uses ATP & NADPH to fix carbon into glucose)."
    ),
    "quadratic equations": (
        "A quadratic equation is a second-order polynomial equation in a single variable: ax^2 + bx + c = 0. "
        "The quadratic formula to find roots is: x = (-b ± √(b^2 - 4ac)) / (2a). "
        "The term (b^2 - 4ac) is called the discriminant (D). If D > 0: two distinct real roots. "
        "If D = 0: one real root. If D < 0: two complex conjugate roots."
    ),
    "python decorators": (
        "A decorator in Python is a function that takes another function as an argument, extends its behavior without "
        "explicitly modifying it, and returns a new function. Syntax: Use '@decorator_name' above the function definition. "
        "Under the hood, @decorator is syntactic sugar for: func = decorator(func)."
    )
}

# Simulated database for scores
QUIZ_SCORES = []

@mcp.tool()
def get_topic_notes(topic: str) -> str:
    """Retrieve study notes and core concepts for a given topic.

    Args:
        topic: The educational topic to look up (e.g., 'photosynthesis', 'quadratic equations', 'python decorators').
    """
    topic_clean = topic.strip().lower()
    for key, notes in STUDY_NOTES.items():
        if key in topic_clean:
            return f"Core Notes for {key.title()}:\n{notes}"
    return f"No pre-defined notes found for '{topic}'. Try asking me to generate custom tutoring notes on this."

@mcp.tool()
def search_study_resources(topic: str) -> list[str]:
    """Search for recommended study materials, websites, and reference links for a topic.

    Args:
        topic: The topic name to find learning resources for.
    """
    topic_clean = topic.strip().lower()
    return [
        f"https://en.wikipedia.org/wiki/{topic_clean.replace(' ', '_')}",
        f"https://www.khanacademy.org/search?referer=%2F&page_search_query={topic_clean.replace(' ', '+')}",
        f"https://www.youtube.com/results?search_query={topic_clean.replace(' ', '+')}+tutorial"
    ]

@mcp.tool()
def record_quiz_score(subject: str, score: float, total_questions: int) -> dict:
    """Record and track a student's quiz score over time.

    Args:
        subject: The subject or topic of the quiz.
        score: The score achieved by the student.
        total_questions: Total number of questions in the quiz.
    """
    percentage = (score / total_questions) * 100 if total_questions > 0 else 0
    record = {
        "subject": subject,
        "score": score,
        "total_questions": total_questions,
        "percentage": percentage
    }
    QUIZ_SCORES.append(record)
    logging.info(f"Recorded quiz score: {record}")
    return {"status": "success", "recorded_entry": record, "all_scores": QUIZ_SCORES}

if __name__ == "__main__":
    mcp.run(transport="stdio")
