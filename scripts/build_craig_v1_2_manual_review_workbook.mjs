import fs from "node:fs/promises";
import path from "node:path";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const root = process.cwd();
const dataPath = path.join(root, "outputs", "craig_v1_2_manual_review_workbook_data.json");
const outputPath = path.join(root, "outputs", "craig_v1_2_manual_chart_review.xlsx");
const previewDir = path.join(root, "outputs", "_review_workbook_previews");

const raw = await fs.readFile(dataPath, "utf8");
const payload = JSON.parse(raw);

function colLetter(n) {
  let s = "";
  while (n > 0) {
    const m = (n - 1) % 26;
    s = String.fromCharCode(65 + m) + s;
    n = Math.floor((n - m) / 26);
  }
  return s;
}

function valuesFromObjects(rows) {
  const headers = Object.keys(rows[0] || {});
  return [headers, ...rows.map((row) => headers.map((h) => row[h] ?? null))];
}

function writeTable(sheet, startRow, startCol, rows, tableName) {
  const matrix = valuesFromObjects(rows);
  const rowCount = matrix.length;
  const colCount = matrix[0]?.length || 1;
  const range = sheet.getRangeByIndexes(startRow, startCol, rowCount, colCount);
  range.values = matrix;
  const endCell = `${colLetter(startCol + colCount)}${startRow + rowCount}`;
  const startCell = `${colLetter(startCol + 1)}${startRow + 1}`;
  const table = sheet.tables.add(`${startCell}:${endCell}`, true, tableName);
  table.showFilterButton = true;
  table.showBandedRows = true;
  return { headers: matrix[0], rowCount, colCount, tableRange: `${startCell}:${endCell}` };
}

function safeSetWidth(sheet, col, width) {
  sheet.getRange(`${col}:${col}`).format.columnWidth = width;
}

function styleReviewSheet(sheet, tableInfo) {
  sheet.showGridLines = false;
  sheet.freezePanes.freezeRows(5);
  sheet.freezePanes.freezeColumns(10);
  sheet.getRange("A1:J1").merge();
  sheet.getRange("A1").values = [["Craig v1.2 Manual Chart Review"]];
  sheet.getRange("A1").format = {
    fill: "#111827",
    font: { bold: true, color: "#FFFFFF", size: 14 },
  };
  sheet.getRange("A2:J3").merge();
  sheet.getRange("A2").values = [[
    "Use the blue editable columns to mark whether Craig would have taken the trade, why not, and what to change. Times are UTC/KST/NY. Chart URL opens the symbol; use trigger/fill timestamps to navigate manually.",
  ]];
  sheet.getRange("A2").format = {
    fill: "#E0F2FE",
    font: { color: "#0F172A" },
    wrapText: true,
  };
  const headerRange = sheet.getRangeByIndexes(4, 0, 1, tableInfo.colCount);
  headerRange.format = {
    fill: "#1F2937",
    font: { bold: true, color: "#FFFFFF" },
    wrapText: true,
  };
  sheet.getRangeByIndexes(5, 0, Math.max(1, tableInfo.rowCount - 1), 8).format = {
    fill: "#DBEAFE",
    font: { color: "#0000FF" },
    wrapText: true,
  };
  sheet.getRangeByIndexes(5, 8, Math.max(1, tableInfo.rowCount - 1), tableInfo.colCount - 8).format = {
    wrapText: false,
  };
  for (const col of ["A", "B", "C", "D", "E", "F"]) safeSetWidth(sheet, col, 15);
  safeSetWidth(sheet, "G", 34);
  safeSetWidth(sheet, "H", 24);
  safeSetWidth(sheet, "I", 18);
  safeSetWidth(sheet, "J", 52);
  safeSetWidth(sheet, "K", 22);
  safeSetWidth(sheet, "L", 48);
  for (const col of ["M", "N", "O", "P", "Q", "R"]) safeSetWidth(sheet, col, 18);
  for (const col of ["S", "T", "U", "V", "W", "X", "Y"]) safeSetWidth(sheet, col, 24);
  for (const col of ["Z", "AA", "AB", "AC", "AD", "AE"]) safeSetWidth(sheet, col, 14);
  sheet.getRangeByIndexes(5, 25, Math.max(1, tableInfo.rowCount - 1), 13).format.numberFormat = "0.000";
  sheet.getRangeByIndexes(5, 50, Math.max(1, tableInfo.rowCount - 1), 6).format.numberFormat = "0.000";

  const dataLastRow = 4 + tableInfo.rowCount;
  const validations = [
    ["A", payload.metadata.validation_lists.review_status],
    ["B", payload.metadata.validation_lists.craig_verdict],
    ["C", payload.metadata.validation_lists.issue_tag],
    ["D", payload.metadata.validation_lists.grade],
    ["E", payload.metadata.validation_lists.grade],
    ["F", payload.metadata.validation_lists.grade],
  ];
  for (const [col, values] of validations) {
    sheet.getRange(`${col}6:${col}${dataLastRow}`).dataValidation = {
      rule: { type: "list", values },
    };
  }
  sheet.getRange(`B6:B${dataLastRow}`).conditionalFormats.add("containsText", {
    text: "would_pass",
    format: { fill: "#FEE2E2", font: { color: "#991B1B" } },
  });
  sheet.getRange(`B6:B${dataLastRow}`).conditionalFormats.add("containsText", {
    text: "would_trade",
    format: { fill: "#DCFCE7", font: { color: "#166534" } },
  });
  sheet.getRange(`Q6:Q${dataLastRow}`).conditionalFormats.add("containsText", {
    text: "stopped",
    format: { fill: "#FEE2E2" },
  });
  sheet.getRange(`Q6:Q${dataLastRow}`).conditionalFormats.add("containsText", {
    text: "runner_hit",
    format: { fill: "#DCFCE7" },
  });
}

function addSummaryBlock(sheet, title, rows, startRow, startCol) {
  const matrix = valuesFromObjects(rows);
  const colCount = matrix[0]?.length || 1;
  sheet.getRangeByIndexes(startRow, startCol, 1, colCount).merge();
  sheet.getRangeByIndexes(startRow, startCol, 1, 1).values = [[title]];
  sheet.getRangeByIndexes(startRow, startCol, 1, colCount).format = {
    fill: "#111827",
    font: { bold: true, color: "#FFFFFF" },
  };
  const range = sheet.getRangeByIndexes(startRow + 1, startCol, matrix.length, colCount);
  range.values = matrix;
  sheet.getRangeByIndexes(startRow + 1, startCol, 1, colCount).format = {
    fill: "#374151",
    font: { bold: true, color: "#FFFFFF" },
  };
  if (matrix.length > 1 && colCount > 2) {
    sheet.getRangeByIndexes(startRow + 2, startCol + 2, matrix.length - 1, colCount - 2).format.numberFormat = "0.000";
  }
  return startRow + matrix.length + 3;
}

const workbook = Workbook.create();

const summary = workbook.worksheets.add("Summary");
summary.showGridLines = false;
summary.getRange("A1:H1").merge();
summary.getRange("A1").values = [["Craig v1.2 Event Backtest Review Workbook"]];
summary.getRange("A1").format = { fill: "#111827", font: { bold: true, color: "#FFFFFF", size: 14 } };

summary.getRange("A3:B10").values = [
  ["Source trade rows", payload.metadata.row_counts.review_all],
  ["S-tier rows", payload.metadata.row_counts.s_tier],
  ["A-tier rows", payload.metadata.row_counts.a_tier],
  ["Gross total R", payload.metadata.headline.gross_total_r],
  ["Net total R", payload.metadata.headline.net_total_r],
  ["Fee drag R", payload.metadata.headline.fee_drag_r],
  ["Slippage drag R", payload.metadata.headline.slippage_drag_r],
  ["Win rate", payload.metadata.headline.win_rate],
];
summary.getRange("A3:A10").format = { fill: "#E5E7EB", font: { bold: true } };
summary.getRange("B3:B9").format.numberFormat = "0.000";
summary.getRange("B10").format.numberFormat = "0.0%";

summary.getRange("D3:E8").values = [
  ["Manual review status", "Count"],
  ["Unchecked", null],
  ["Reviewed", null],
  ["Would trade", null],
  ["Would pass", null],
  ["Maybe/unclear", null],
];
summary.getRange("D3:E3").format = { fill: "#374151", font: { bold: true, color: "#FFFFFF" } };
summary.getRange("D4:D8").format = { fill: "#E0F2FE", font: { bold: true } };
summary.getRange("E4:E8").format.numberFormat = "#,##0";

let row = 12;
row = addSummaryBlock(summary, "By Final State", payload.summary_by_state, row, 0);
row = addSummaryBlock(summary, "By Entry Tier", payload.summary_by_tier, row, 0);
row = addSummaryBlock(summary, "By Symbol/Side", payload.summary_by_symbol_side, row, 0);
row = addSummaryBlock(summary, "By Session", payload.summary_by_session, row, 0);
row = addSummaryBlock(summary, "By Scenario Type", payload.summary_by_scenario, row, 0);
summary.getUsedRange().format.autofitColumns();
summary.getUsedRange().format.autofitRows();

const review = workbook.worksheets.add("Review_All");
const reviewInfo = writeTable(review, 4, 0, payload.review_rows, "ReviewAllTable");
styleReviewSheet(review, reviewInfo);

const priority = workbook.worksheets.add("Priority_Review");
const priorityInfo = writeTable(priority, 4, 0, payload.priority_rows, "PriorityReviewTable");
styleReviewSheet(priority, priorityInfo);
priority.getRange("A1").values = [["Craig v1.2 Priority Chart Review Queue"]];
priority.getRange("A2").values = [[
  "Subset of S-tier, high-cost stops, BE fee bleed, winners, and no-chase rows. Use Review_All for the full 1,390-row source.",
]];

const lists = workbook.worksheets.add("Lists");
lists.showGridLines = false;
const listRows = [
  ["review_status", ...payload.metadata.validation_lists.review_status],
  ["craig_verdict", ...payload.metadata.validation_lists.craig_verdict],
  ["issue_tag", ...payload.metadata.validation_lists.issue_tag],
  ["grade", ...payload.metadata.validation_lists.grade],
];
const maxLen = Math.max(...listRows.map((r) => r.length));
const padded = listRows.map((r) => [...r, ...Array(maxLen - r.length).fill(null)]);
lists.getRangeByIndexes(0, 0, padded.length, maxLen).values = padded;
lists.getRangeByIndexes(0, 0, padded.length, 1).format = { fill: "#E5E7EB", font: { bold: true } };
lists.getUsedRange().format.autofitColumns();

const sources = workbook.worksheets.add("Sources");
sources.showGridLines = false;
sources.getRange("A1:C1").values = [["Item", "Path", "Notes"]];
sources.getRange("A1:C1").format = { fill: "#111827", font: { bold: true, color: "#FFFFFF" } };
sources.getRange("A2:C7").values = [
  ["Trade log", payload.metadata.generated_from.trade_log, "Event-driven execution simulator output"],
  ["Sniper candidates", payload.metadata.generated_from.sniper_candidates, "v1.2.1 S/A candidate source"],
  ["Scenario thesis", payload.metadata.generated_from.scenario_thesis, "Scenario/PA zone context"],
  ["Event report", payload.metadata.generated_from.event_report, "Summary report used for headline stats"],
  ["Workbook purpose", "manual chart review", "Editable blue columns are for user notes and verdicts"],
  ["No-lookahead note", "source outputs report 0 violations", "Workbook does not add new model logic"],
];
sources.getUsedRange().format.autofitColumns();
sources.getUsedRange().format.autofitRows();

summary.getRange("E4:E8").formulas = [
  ["=COUNTIF('Review_All'!A6:A1395,\"unchecked\")+COUNTBLANK('Review_All'!A6:A1395)"],
  ["=COUNTIF('Review_All'!A6:A1395,\"reviewed\")"],
  ["=COUNTIF('Review_All'!B6:B1395,\"would_trade\")"],
  ["=COUNTIF('Review_All'!B6:B1395,\"would_pass\")"],
  ["=COUNTIF('Review_All'!B6:B1395,\"maybe\")+COUNTIF('Review_All'!B6:B1395,\"unclear\")"],
];

await fs.mkdir(previewDir, { recursive: true });
for (const spec of [
  ["Summary", "A1:H35", "summary.png"],
  ["Review_All", "A1:Z25", "review_all.png"],
  ["Priority_Review", "A1:Z25", "priority_review.png"],
  ["Lists", "A1:Q8", "lists.png"],
  ["Sources", "A1:C8", "sources.png"],
]) {
  const [sheetName, range, filename] = spec;
  const preview = await workbook.render({ sheetName, range, scale: 1, format: "png" });
  await fs.writeFile(path.join(previewDir, filename), new Uint8Array(await preview.arrayBuffer()));
}

const errorScan = await workbook.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
  options: { useRegex: true, maxResults: 100 },
  summary: "formula error scan",
});
console.log(errorScan.ndjson);

const check = await workbook.inspect({
  kind: "table",
  sheetId: "Review_All",
  range: "A5:J12",
  include: "values",
  tableMaxRows: 8,
  tableMaxCols: 10,
});
console.log(check.ndjson);

const xlsx = await SpreadsheetFile.exportXlsx(workbook);
await xlsx.save(outputPath);
console.log(`Saved ${outputPath}`);
