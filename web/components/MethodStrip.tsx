import type { Summary } from "@/lib/api";

export function MethodStrip({ summary }: { summary: Summary }) {
  return (
    <div className="method">
      <div>
        <div className="k">Held-out test</div>
        <div className="v">
          {summary.split.test} runs the optimizer never saw ({Math.round(summary.split.test_fraction * 100)}% of {summary.split.test + summary.split.optimization})
        </div>
      </div>
      <div>
        <div className="k">Scoring</div>
        <div className="v">
          {summary.scoring === "ground_truth"
            ? "Automatic checks + each task's correct answer, graded by the agent's own grader (no LLM judge)"
            : summary.scoring === "mixed"
            ? `Each task's correct answer where it has one; otherwise ${summary.judge.model} judging both answers blind`
            : `Automatic checks + ${summary.judge.model} judging both answers blind, in random order`}
        </div>
      </div>
      <div>
        <div className="k">Cost</div>
        <div className="v">Token Factory list prices × recorded tokens, served via {summary.provider === "ollama" ? "Ollama Cloud" : summary.provider}</div>
      </div>
      <div>
        <div className="k">Budget</div>
        <div className="v">
          {summary.budget.rounds} rounds × {summary.budget.sample_size} runs per option, capped at ${summary.budget.max_cost_usd}
        </div>
      </div>
    </div>
  );
}
