"""CLI runner: takes a candidate_id and prints the generated report."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from src.agent import build_graph
from src.models import CandidateProfile


def run_for(candidate_id: str, data_dir: Path = Path("data/candidates")) -> dict:
    profile_path = data_dir / candidate_id / "profile.json"
    if not profile_path.exists():
        raise SystemExit(f"No profile found for {candidate_id} at {profile_path}")

    candidate = CandidateProfile(**json.loads(profile_path.read_text(encoding="utf-8")))

    # Raw documents: todo lo que acompaña al candidato en su carpeta menos
    # el profile y el transcript. Aquí declaramos el tipo explícito para
    # que el mock extractor los lea desde su filename.
    raw_docs = []
    for path in sorted((data_dir / candidate_id).iterdir()):
        name = path.name
        if name in ("profile.json", "transcript.txt"):
            continue
        if "cv" in name.lower():
            doc_type = "cv"
        elif "cert" in name.lower():
            doc_type = "certificate"
        elif "id" in name.lower() or "passport" in name.lower():
            doc_type = "id"
        elif "portfolio" in name.lower():
            doc_type = "portfolio"
        elif "reference" in name.lower() or "ref" in name.lower():
            doc_type = "reference"
        else:
            doc_type = "other"
        raw_docs.append({"doc_type": doc_type, "filename": name})

    graph = build_graph()
    final_state = graph.invoke({
        "candidate": candidate,
        "video_url": f"https://hireflix.example/videos/{candidate_id}.mp4",
        "raw_documents": raw_docs,
    })

    report = final_state["report"]
    return report.model_dump(mode="json")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Run the onboarding agent for a candidate.")
    parser.add_argument("candidate_id", help="ID of candidate folder under data/candidates/")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print the JSON output")
    args = parser.parse_args(argv)

    report = run_for(args.candidate_id)
    indent = 2 if args.pretty else None
    json.dump(report, sys.stdout, ensure_ascii=False, indent=indent, default=str)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
