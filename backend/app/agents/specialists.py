"""Bốn Agent cốt lõi của MVP. Mỗi Agent chỉ làm việc thông qua công cụ được cấp phép (tools.py)."""
from __future__ import annotations

from .base import BaseAgent, StepResult, TaskContext

SOURCE_LABELS = {"weather": "thời tiết", "water": "điểm nước đọng", "survey": "khảo sát thực địa"}


class DataAgent(BaseAgent):
    name = "Data Agent"
    role = "Truy xuất, kiểm tra và chuẩn hóa dữ liệu"

    def retrieve(self, ctx: TaskContext) -> StepResult:
        parts, sources, skipped = [], set(), []
        if "weather" in ctx.sources:
            out = self.call(ctx, "get_weather_data", area_ids=ctx.area_ids, start=ctx.start, end=ctx.end)
            parts.append(out["summary"]); sources.update(out["sources"])
            ctx.state["weather_rows"] = len(out["rows"])
        else:
            skipped.append("thời tiết")
        if "water" in ctx.sources:
            out = self.call(ctx, "get_water_points", area_ids=ctx.area_ids, end=ctx.end)
            parts.append(out["summary"]); sources.update(out["sources"])
        else:
            skipped.append("điểm nước đọng")
        if "survey" in ctx.sources:
            out = self.call(ctx, "get_survey_data", area_ids=ctx.area_ids, end=ctx.end, species=ctx.species)
            parts.append(out["summary"]); sources.update(out["sources"])
        else:
            skipped.append("khảo sát thực địa")
        ctx.state["data_sources"] = sorted(sources)
        warnings = [f"Không truy xuất nguồn: {', '.join(skipped)} (người dùng không chọn)."] if skipped else []
        return StepResult("; ".join(parts) + ".", {"sources": sorted(sources), "skipped": skipped}, warnings)

    def validate(self, ctx: TaskContext) -> StepResult:
        out = self.call(ctx, "validate_dataset", area_ids=ctx.area_ids, start=ctx.start, end=ctx.end,
                        species=ctx.species, sources=ctx.sources)
        ctx.state["data_issues"] = out["issues"]
        return StepResult(out["summary"] + ".", {"per_area": out["per_area"]}, out["issues"][:20])


class EnvironmentalAnalysisAgent(BaseAgent):
    name = "Environmental Analysis Agent"
    role = "Tạo đặc trưng và gọi scoring service (ESS/PIS)"

    def analyze(self, ctx: TaskContext) -> StepResult:
        results = []
        for area_id in ctx.area_ids:
            results.append(self.call(ctx, "compute_environmental_score", area_id=area_id, start=ctx.start, end=ctx.end,
                                     species=ctx.species, sources=ctx.sources, task_id=ctx.task_id, user_name=ctx.user_name))
        ctx.state["results"] = results
        scored = [r for r in results if r["ess"] is not None]
        not_scored = len(results) - len(scored)
        summary = f"Đã tính ESS/PIS cho {len(scored)}/{len(results)} khu vực bằng scoring service"
        if scored:
            summary += f" (ESS cao nhất {max(r['ess'] for r in scored):g}, thấp nhất {min(r['ess'] for r in scored):g})"
        warnings = [f"{not_scored} khu vực không đủ dữ liệu để tính ESS — không suy diễn điểm."] if not_scored else []
        return StepResult(summary + ".", {"run_ids": [r["run_id"] for r in results],
                                          "scoring_version": results[0]["scoring_version"] if results else None}, warnings)


class GeospatialAgent(BaseAgent):
    name = "Geospatial Agent"
    role = "Liên kết kết quả với vị trí và chuẩn bị lớp bản đồ"

    def map_results(self, ctx: TaskContext) -> StepResult:
        out = self.call(ctx, "build_map_layer", results=[{"area_id": r["area_id"], "ess": r["ess"], "pis": r["pis"]}
                                                         for r in ctx.state["results"]], end=ctx.end)
        ctx.state["map_layer"] = out["features"]
        warnings = [f"{out['unmatched_points']} điểm nước đọng không nằm trong ranh giới khu vực được gán."] if out["unmatched_points"] else []
        return StepResult(out["summary"] + ".", {"features": out["features"]}, warnings)


class RiskAlertAgent(BaseAgent):
    name = "Risk & Alert Agent"
    role = "Tổng hợp, xếp hạng ưu tiên và tạo đề xuất (chờ người duyệt)"

    def propose(self, ctx: TaskContext) -> StepResult:
        results = ctx.state["results"]
        ranking = self.call(ctx, "rank_priority_locations", results=results)
        ctx.state["ranking"] = ranking["ranking"]
        proposals = self.call(ctx, "create_alert_proposals", results=results, task_id=ctx.task_id, user_name=ctx.user_name)
        ctx.state["alerts"] = proposals["alerts"]
        top = ", ".join(f"{r['area_code']} (PIS {r['pis']:g})" for r in ranking["ranking"][:3]) or "không có"
        return StepResult(
            f"{ranking['summary']}. Ưu tiên cao nhất: {top}. {proposals['summary']}.",
            {"ranking": ranking["ranking"], "not_scored": ranking["not_scored"],
             "alert_codes": [a["code"] for a in proposals["alerts"]]},
        )
