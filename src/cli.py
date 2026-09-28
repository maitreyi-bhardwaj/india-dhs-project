"""Ask the system a question from the terminal.

    python -m src.cli "What does v012 mean?"
    python -m src.cli --offline "Which population appears most underserved?"
"""

import argparse

from src.agents.orchestrator import answer_question
from src.agents.synthesis import evidence_markdown


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("question")
    parser.add_argument("--offline", action="store_true", help="never call the LLM, even if a key is set")
    args = parser.parse_args()
    answer = answer_question(args.question, llm=None if args.offline else "auto")
    print(f"# {answer.question}\n\n_mode: {answer.mode}; {answer.trace.to_dict()['seconds']}s_\n")
    print(answer.markdown)
    print()
    print(evidence_markdown(answer.trace))


if __name__ == "__main__":
    main()
