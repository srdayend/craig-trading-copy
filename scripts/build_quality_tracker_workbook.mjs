import fs from "node:fs/promises";
import path from "node:path";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const root = path.resolve(".");
const outputDir = path.join(root, "outputs", "craig_quality_tracker_v0_3");
const inputPath = path.join(outputDir, "quality_tracker_inputs.json");
const outputPath = path.join(outputDir, "craig_video_quality_tracker_v0_3.xlsx");

const raw = JSON.parse(await fs.readFile(inputPath, "utf8"));

const workbook = Workbook.create();

function addTitle(sheet, title, subtitle = "") {
  sheet.getRange("A1:K1").merge();
  sheet.getRange("A1").values = [[title]];
  sheet.getRange("A1").format = {
    fill: "#12343B",
    font: { bold: true, color: "#FFFFFF", size: 14 },
  };
  if (subtitle) {
    sheet.getRange("A2:K2").merge();
    sheet.getRange("A2").values = [[subtitle]];
    sheet.getRange("A2").format = {
      fill: "#EAF3F5",
      font: { color: "#12343B", size: 10 },
    };
  }
  sheet.showGridLines = false;
}

function writeTable(sheet, startCell, headers, rows, tableName) {
  const start = addressToIndex(startCell);
  const matrix = [headers, ...rows.map((row) => headers.map((h) => row[h] ?? ""))];
  const range = sheet.getRangeByIndexes(start.row, start.col, matrix.length, headers.length);
  range.values = matrix;
  const headerRange = sheet.getRangeByIndexes(start.row, start.col, 1, headers.length);
  headerRange.format = {
    fill: "#1F6F78",
    font: { bold: true, color: "#FFFFFF" },
    wrapText: true,
  };
  const bodyRange = sheet.getRangeByIndexes(start.row + 1, start.col, Math.max(rows.length, 1), headers.length);
  bodyRange.format = {
    wrapText: true,
    borders: {
      insideHorizontal: { style: "thin", color: "#E5E7EB" },
      insideVertical: { style: "thin", color: "#F1F5F9" },
      bottom: { style: "thin", color: "#CBD5E1" },
    },
  };
  if (rows.length) {
    const tableRange = range.address;
    const table = sheet.tables.add(tableRange, true, tableName);
    table.style = "TableStyleMedium2";
  }
  return range;
}

function addressToIndex(address) {
  const match = /^([A-Z]+)(\d+)$/i.exec(address);
  if (!match) throw new Error(`Bad address: ${address}`);
  const letters = match[1].toUpperCase();
  let col = 0;
  for (const ch of letters) col = col * 26 + (ch.charCodeAt(0) - 64);
  return { row: Number(match[2]) - 1, col: col - 1 };
}

function setWidths(sheet, widths) {
  widths.forEach((width, index) => {
    sheet.getRangeByIndexes(0, index, 1, 1).format.columnWidth = width;
  });
}

function summaryRows(summary) {
  const stage = Object.entries(summary.stage_summary).map(([k, v]) => ({
    구분: k,
    개수: v,
    비고: "quality_level 기준",
  }));
  const actions = Object.entries(summary.action_summary).map(([k, v]) => ({
    구분: k,
    개수: v,
    비고: "next_action 기준",
  }));
  return [
    { 구분: "local_video_count", 개수: summary.local_video_count, 비고: "로컬 mp4" },
    { 구분: "local_srt_count", 개수: summary.local_srt_count, 비고: "로컬 srt" },
    { 구분: "matched_video_id_count", 개수: summary.matched_video_id_count, 비고: "details.csv 매칭" },
    ...stage,
    ...actions,
  ];
}

const dashboard = workbook.worksheets.add("Dashboard");
addTitle(
  dashboard,
  "Craig Trading Copy - Video Quality Tracker v0.3",
  "로컬 영상/SRT/기존 산출물을 기준으로, 현재 품질 상태와 다음 작업을 추적합니다.",
);
const summaryHeaders = ["구분", "개수", "비고"];
writeTable(dashboard, "A4", summaryHeaders, summaryRows(raw.scope_summary), "DashboardSummaryTable");
dashboard.getRange("A4:C4").format = {
  fill: "#12343B",
  font: { bold: true, color: "#FFFFFF" },
};
dashboard.getRange("E4:K12").values = [
  ["v0.3 품질 기준", "", "", "", "", "", ""],
  ["핵심 변화", "매크로/HFT, daily bias, 시나리오, Elliott/Fib, 실시간 의견 변경을 trade row와 분리/연결", "", "", "", "", ""],
  ["Gold-ready", "G01-G13을 충족하고 UTC-4 시간 + 1m OHLCV + 프레임/recap 증거가 모순 없음", "", "", "", "", ""],
  ["보강 대상", "기존 정식 3개도 폐기 대상은 아니지만, v0.3 스키마 승격 대상", "", "", "", "", ""],
  ["로컬 원칙", "이제 YouTube 접속 없이 mp4+srt+차트 데이터로 작업", "", "", "", "", ""],
  ["주의", "C3-ZcTx1mpE 등 로컬 영상에 없는 항목은 현재 scope에서 제외", "", "", "", "", ""],
  ["업데이트", raw.scope_summary.generated_at, "", "", "", "", ""],
  ["", "", "", "", "", "", ""],
  ["", "", "", "", "", "", ""],
];
dashboard.getRange("E4:K4").merge();
dashboard.getRange("E4").format = { fill: "#1F6F78", font: { bold: true, color: "#FFFFFF" } };
dashboard.getRange("E5:K11").format = { wrapText: true, fill: "#F8FAFC" };
setWidths(dashboard, [28, 12, 42, 3, 20, 36, 14, 14, 14, 14, 14]);
dashboard.freezePanes.freezeRows(4);

const progress = workbook.worksheets.add("Progress_Index");
addTitle(
  progress,
  "Video Index And Quality Status",
  "영상 하나를 작업 단위로 보며, Q3는 기존 정식 품질, Q2/Q1/Q0는 v0.3로 끌어올릴 대상입니다.",
);
const progressHeaders = [
  "local_index_oldest_first",
  "video_id",
  "video_title",
  "upload_date",
  "duration",
  "asset_ready",
  "quality_level",
  "quality_score",
  "working_status",
  "next_action",
  "manual_seed_rows",
  "bdg_partial_rows",
  "pilot3_rows",
  "frame_data_rows",
  "remaining_auto_rows",
  "v03_session_rows",
  "v03_context_rows",
  "v03_hold_rows",
  "v03_rule_rows",
  "verified_market_date",
  "market_date_source",
  "macro_status_v0_3",
  "elliott_status_v0_3",
  "time_data_status",
  "entry_sl_tp_status",
  "result_status",
  "macro_hft_term_hits",
  "elliott_wave_fib_term_hits",
  "setup_term_hits",
  "execution_management_term_hits",
  "video_file",
  "srt_file",
  "gap_note",
];
writeTable(progress, "A4", progressHeaders, raw.videos, "ProgressIndexTable");
progress.freezePanes.freezeRows(4);
progress.freezePanes.freezeColumns(3);
setWidths(progress, [
  10, 14, 48, 12, 10, 14, 32, 10, 16, 24, 10, 10, 10, 10, 10, 10, 10, 10, 10, 14, 24, 22, 22, 22, 24, 18, 10, 10, 10, 10, 48, 48, 72,
]);
progress.getRange(`I5:I${raw.videos.length + 4}`).dataValidation = {
  rule: { type: "list", values: ["대기", "진행중", "검증필요", "보강필요", "완료", "완료/hold있음", "보류"] },
};
progress.getRange(`H5:H${raw.videos.length + 4}`).format.numberFormat = "0";
progress.getRange(`K5:S${raw.videos.length + 4}`).format.numberFormat = "0";
progress.getRange(`AA5:AD${raw.videos.length + 4}`).format.numberFormat = "0";

const quality = workbook.worksheets.add("Quality_Gates");
addTitle(
  quality,
  "v0.3 Quality Gates",
  "Gold-ready 승격 전 반드시 확인해야 하는 정보 카테고리입니다.",
);
const gateRows = raw.quality_gates.map((r) => ({
  gate_id: r[0],
  category: r[1],
  required_evidence: r[2],
  pass_condition: r[3],
}));
writeTable(quality, "A4", ["gate_id", "category", "required_evidence", "pass_condition"], gateRows, "QualityGatesTable");
quality.freezePanes.freezeRows(4);
setWidths(quality, [12, 26, 54, 72]);

const model = workbook.worksheets.add("Extraction_Model_v0_3");
addTitle(
  model,
  "Upgraded Extraction Model v0.3",
  "새 영상과 보강 영상 모두 같은 단계로 처리합니다.",
);
const stepRows = raw.extraction_steps.map((r) => ({
  step: r[0],
  name: r[1],
  action: r[2],
  output: r[3],
}));
writeTable(model, "A4", ["step", "name", "action", "output"], stepRows, "ExtractionModelTable");
model.freezePanes.freezeRows(4);
setWidths(model, [8, 24, 82, 34]);

const audit = workbook.worksheets.add("Category_Audit");
addTitle(
  audit,
  "Missing Category Audit",
  "크레이그를 더 가깝게 복제하기 위해 v0.2에서 덜 분리되어 있던 정보입니다.",
);
const auditRows = raw.category_audit.map((r) => ({
  category: r[0],
  current_gap: r[1],
  v0_3_fix: r[2],
}));
writeTable(audit, "A4", ["category", "current_gap", "v0_3_fix"], auditRows, "CategoryAuditTable");
audit.freezePanes.freezeRows(4);
setWidths(audit, [30, 70, 70]);

const terms = workbook.worksheets.add("Transcript_Term_Scan");
addTitle(
  terms,
  "SRT Term Scan",
  "SRT 전체를 가볍게 훑어 macro/wave/setup/management 관련 발화 밀도를 추적합니다. 0은 부재 확정이 아니라 정독 필요 신호입니다.",
);
const termHeaders = [
  "local_index_oldest_first",
  "video_id",
  "video_title",
  "macro_hft_term_hits",
  "session_term_hits",
  "symbol_selection_term_hits",
  "elliott_wave_fib_term_hits",
  "setup_term_hits",
  "execution_management_term_hits",
  "quality_level",
];
writeTable(terms, "A4", termHeaders, raw.videos, "TranscriptTermScanTable");
terms.freezePanes.freezeRows(4);
terms.freezePanes.freezeColumns(3);
setWidths(terms, [10, 14, 52, 14, 14, 16, 16, 14, 18, 28]);
terms.getRange(`D5:I${raw.videos.length + 4}`).format.numberFormat = "0";

const schema = workbook.worksheets.add("Target_Fields_v0_3");
addTitle(
  schema,
  "Target Fields v0.3",
  "다음 context CSV는 아래 필드들을 기준으로 확장하면 됩니다.",
);
const targetFields = [
  ["session_context_id", "영상/하루 단위 ID"],
  ["video_id", "YouTube video id / local metadata id"],
  ["video_title", "영상 제목"],
  ["local_video_path", "로컬 mp4 경로"],
  ["local_srt_path", "로컬 srt 경로"],
  ["market_dates_utc_minus4", "실제 거래 날짜"],
  ["session_macro_context_ko", "HFT/daily bias/뉴스/주요 레벨"],
  ["scenario_tree_ko", "롱/숏/대기 조건부 시나리오"],
  ["symbol_selection_context_ko", "BTC/ETH/SOL 상대 강약 및 선택 이유"],
  ["elliott_wave_context_ko", "wave count, extension, invalidation"],
  ["decision_context_id", "각 trade/setup/pass decision unit"],
  ["decision_type", "executed/no_fill/cancel/pass/reentry/manage_change"],
  ["trade_thesis_link_ko", "이 decision이 session macro/wave 중 무엇을 사용했는지"],
  ["chart_timeframe", "1m/3m/5m/15m/4h 등"],
  ["structure_reference_ko", "SR/FVG/CHoCH/trendline이 어떤 캔들/존 기준인지"],
  ["entry_plan_ko", "entry/SL/TP/R/R과 주문 의도"],
  ["management_plan_ko", "BE/trail/partial/manual close 조건"],
  ["live_thesis_changes_ko", "실시간 의견 변화와 트리거"],
  ["exit_result_ko", "손절/익절/BE/no-fill/cancel/result"],
  ["ohlcv_alignment_ko", "1분봉 데이터 대조"],
  ["rule_feature_vector_seed_ko", "정량화 후보 feature"],
  ["invalidation_condition_ko", "셋업 무효화 조건"],
  ["remaining_uncertainty_ko", "불확실성 및 gold 보류 이유"],
];
writeTable(
  schema,
  "A4",
  ["field", "description"],
  targetFields.map((r) => ({ field: r[0], description: r[1] })),
  "TargetFieldsTable",
);
schema.freezePanes.freezeRows(4);
setWidths(schema, [34, 88]);

for (const sheet of workbook.worksheets.items) {
  const used = sheet.getUsedRange();
  if (used) {
    used.format.font = { name: "Aptos", size: 10 };
  }
}

await fs.mkdir(outputDir, { recursive: true });

const inspectProgress = await workbook.inspect({
  kind: "table",
  sheetId: "Progress_Index",
  range: "A4:J12",
  include: "values,formulas",
  tableMaxRows: 12,
  tableMaxCols: 10,
  maxChars: 4000,
});
console.log(inspectProgress.ndjson);

const errors = await workbook.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
  options: { useRegex: true, maxResults: 300 },
  summary: "final formula error scan",
});
console.log(errors.ndjson);

for (const sheetName of [
  "Dashboard",
  "Progress_Index",
  "Quality_Gates",
  "Extraction_Model_v0_3",
  "Category_Audit",
  "Transcript_Term_Scan",
  "Target_Fields_v0_3",
]) {
  const preview = await workbook.render({
    sheetName,
    autoCrop: "all",
    scale: 1,
    format: "png",
  });
  await fs.writeFile(
    path.join(outputDir, `${sheetName}.png`),
    new Uint8Array(await preview.arrayBuffer()),
  );
}

const xlsx = await SpreadsheetFile.exportXlsx(workbook);
await xlsx.save(outputPath);
console.log(outputPath);
