"""Generate remaining_tables.json by comparing full list with extracted tables."""
import json
import re

# Read the plan file to get all 613 US4G table names
with open('SAP_KNOWLEDGE_EXTRACTION_PLAN.md', 'r', encoding='utf-8') as f:
    plan_text = f.read()

# Extract table names from the code block
all_us4g = set()
for match in re.findall(r'/US4G/[A-Z0-9_]+', plan_text):
    all_us4g.add(match)

# Load extracted tables
with open('us4g_field_metadata_380_tables.json', 'r', encoding='utf-8') as f:
    extracted = json.load(f)
done_us4g = set(extracted.get('tabellen', {}).keys())

# Calculate remaining US4G
remaining_us4g = sorted(all_us4g - done_us4g)

# EMMA tables (all need extraction)
emma_tables = [
    "EMMAC_BASIC", "EMMAC_BPA", "EMMAC_BPC", "EMMAC_BPC_PROCID", "EMMAC_CANCODE",
    "EMMAC_CANCODET", "EMMAC_CCAT_BND", "EMMAC_CCAT_CND", "EMMAC_CCAT_COB",
    "EMMAC_CCAT_HDR", "EMMAC_CCAT_HDRT", "EMMAC_CCAT_MOB", "EMMAC_CCAT_MSG",
    "EMMAC_CCAT_PRI", "EMMAC_CCAT_SOP", "EMMAC_CCAT_SOP_B", "EMMAC_CCSTATUS",
    "EMMAC_CCSTATUST", "EMMAC_CREACODE", "EMMAC_CREACODET", "EMMAC_CSTAT_ASS",
    "EMMAC_CTYPE", "EMMAC_CTYPET", "EMMAC_CWL_BTN", "EMMAC_CWL_BTNT", "EMMAC_CWL_SHL",
    "EMMAC_CWL_SHLT", "EMMAC_FWM", "EMMAC_FWMT", "EMMAC_FWM_ACTION", "EMMAC_MSGSUPRS",
    "EMMAC_MSG_OBJ", "EMMAC_MSG_SUPRES", "EMMAC_SOPTXTID", "EMMAC_SOPTXTIDT",
    "EMMAC_WUI_CCAT", "EMMAC_WUI_OBJ", "EMMAC_WUI_PROC", "EMMAC_WUI_REP",
    "EMMAC_WUI_REPT", "EMMA_BPA", "EMMA_BPAT", "EMMA_BPC", "EMMA_BPCT", "EMMA_CACTOR",
    "EMMA_CACTOR_CD", "EMMA_CASE", "EMMA_CMSG_LINK", "EMMA_CMSG_LNK_CD",
    "EMMA_COBJECT", "EMMA_COBJECT_CD", "EMMA_CSOLP", "EMMA_HDR", "EMMA_INT",
    "EMMA_JOBRUNIDMSG", "EMMA_MASSACT_INF", "EMMA_TCODE"
]

# Classic IS-U tables (all need extraction)
isu_tables = [
    "EANL", "EANLD", "EANLD1", "EANLDATA", "EANLDATASAP", "EANLH", "EANLHD", "EANLHDATA",
    "EANLHDATASAP", "EANLHKEY", "EUIINSTLN", "EUIINSTLN_DATA", "EUIINSTLN_DATA_PROFSEL",
    "EUIINSTLN_KEY", "EUIINSTLN_KEY_PROFSEL", "EUIINSTLN_PROFSEL", "EUITRANS",
    "EUITRANS_DATA", "EUITRANS_DATA_OP", "EUITRANS_DATA_PROFSEL", "EUITRANS_KEY",
    "EUITRANS_KEY_PROFSEL", "EUITRANS_PROFSEL", "EVBS", "EVBSCOND", "EVBSD", "EVBSD1",
    "EVBST", "EVBS_OHNE_CI_INCLUDE", "ESERVICE", "ESERVICED", "ESERVICEDET",
    "ESERVICEDOCITM", "ESERVICEDOCUMENT", "ESERVICEKEY", "ESERVICE_DEFAULTING",
    "ESERVPROV", "ESERVPROV001QR", "ESERVPROV001QR_APPLDATA_IN",
    "ESERVPROV001QR_APPLDATA_OUT", "ESERVPROVBDIDQR_APPLDATA_IN", "ERCH", "ERCHARC",
    "ERCHC", "ERCHC_DISP", "ERCHC_DISP_SEL", "ERCHC_SHORT", "ERCHC_STABLE", "ERCHE",
    "ERCHE_I1", "ERCHE_M18", "ERCHE_STABLE", "ERCHH", "ERCHO", "ERCHOD", "ERCHO_STABLE",
    "ERCHP", "ERCHP_STABLE", "ERCHR", "ERCHR_I", "ERCHR_STABLE", "ERCHT", "EVERSREASON",
    "EVERSREASONT", "EVERSW"
]

# Create output
result = {
    "generated_at": "2026-01-07",
    "summary": {
        "us4g_remaining": len(remaining_us4g),
        "emma_remaining": len(emma_tables),
        "isu_remaining": len(isu_tables),
        "total": len(remaining_us4g) + len(emma_tables) + len(isu_tables)
    },
    "us4g_remaining": remaining_us4g,
    "emma_remaining": emma_tables,
    "isu_remaining": isu_tables,
    "batches": {
        "us4g": [remaining_us4g[i:i+20] for i in range(0, len(remaining_us4g), 20)],
        "emma": [emma_tables[i:i+20] for i in range(0, len(emma_tables), 20)],
        "isu": [isu_tables[i:i+20] for i in range(0, len(isu_tables), 20)]
    }
}

# Write output
with open('remaining_tables.json', 'w', encoding='utf-8') as f:
    json.dump(result, f, indent=2, ensure_ascii=False)

print(f"Total US4G in plan: {len(all_us4g)}")
print(f"Already extracted: {len(done_us4g)}")
print(f"Remaining US4G: {len(remaining_us4g)}")
print(f"EMMA tables: {len(emma_tables)}")
print(f"ISU tables: {len(isu_tables)}")
print(f"TOTAL remaining: {result['summary']['total']}")
print(f"\nBatches created:")
print(f"  US4G: {len(result['batches']['us4g'])} batches")
print(f"  EMMA: {len(result['batches']['emma'])} batches")
print(f"  ISU: {len(result['batches']['isu'])} batches")
print(f"\nFirst US4G batch (20 tables):")
if result['batches']['us4g']:
    for t in result['batches']['us4g'][0]:
        print(f"  {t}")
