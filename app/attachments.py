import base64

from app.clients import deploy_client
from app.config import MAX_ATTACHMENT_CHARS, SCREENSHOT_MODEL
from app.retrieval import extract_json_object, extract_model_text, format_screenshot_triage

def extract_text_from_attachment(uploaded_file):
    if not uploaded_file:
        return ""

    file_name = uploaded_file.name
    file_type = uploaded_file.type or ""
    lower_name = file_name.lower()

    if lower_name.endswith((".txt", ".log", ".json", ".sql", ".py", ".yml", ".yaml", ".md", ".csv")):
        try:
            raw = uploaded_file.getvalue().decode("utf-8", errors="ignore")
            text = raw[:MAX_ATTACHMENT_CHARS].strip()

            if not text:
                return f"ATTACHMENT_TEXT_EMPTY\nFile: {file_name}\nNo readable text was found."

            return f"ATTACHMENT_TEXT_EXTRACTED\nFile: {file_name}\n\n{text}"

        except Exception as e:
            return f"ATTACHMENT_TEXT_ERROR\nFile: {file_name}\nError: {str(e)}"

    if lower_name.endswith((".png", ".jpg", ".jpeg")) or file_type.startswith("image/"):
        if deploy_client is None:
            return (
                f"ATTACHMENT_OCR_ERROR\n"
                f"File: {file_name}\n"
                "The Databricks model client is not configured. Configure the Databricks connection settings, "
                "or paste the visible screenshot text directly into chat."
            )

        if not SCREENSHOT_MODEL:
            return (
                f"ATTACHMENT_OCR_NOT_CONFIGURED\n"
                f"File: {file_name}\n"
                "A screenshot was attached, but SCREENSHOT_MODEL is not configured. "
                "Ask the user to paste the visible error text. Do not infer error codes."
            )

        try:
            file_bytes = uploaded_file.getvalue()
            encoded = base64.b64encode(file_bytes).decode("utf-8")
            mime_type = file_type or "image/png"

            ocr_prompt = """
You are a screenshot auto-triage helper for an Azure Databricks and Microsoft Fabric SME support app.

Task:
- Transcribe visible screenshot text as accurately as possible.
- Identify the likely product area, UI area, symptom, severity, and troubleshooting topic.
- Do NOT solve the issue.
- Do NOT invent error codes, object names, workspace names, or UI labels.
- If unreadable, set visible_text to OCR_FAILED_UNREADABLE_IMAGE and confidence to low.

Use only these likely_topic values when possible:
- cluster_bootstrap
- adls_private_access
- unity_catalog_setup
- fabric_mirroring
- fabric_lakehouse
- fabric_warehouse
- fabric_pipeline
- fabric_onelake
- fabric_capacity
- spark_performance
- compliance_architecture
- model_serving
- sql_warehouse
- lakeflow
- general

Use only these likely_intent values when possible:
- deep_troubleshooting
- deep_implementation
- deep_integration
- deep_architecture
- learning
- explanation

Return strict JSON only with this schema:
{
    "visible_text": "string",
    "product_area": "string",
    "ui_area": "string",
    "detected_symptom": "string",
    "error_codes": ["string"],
    "object_names": {
        "workspace": "string",
        "cluster": "string",
        "catalog": "string",
        "schema": "string",
        "table": "string",
        "pipeline": "string",
        "endpoint": "string"
    },
    "likely_topic": "string",
    "likely_intent": "string",
    "severity": "low|medium|high|unknown",
    "confidence": "low|medium|high",
    "missing_info": ["string"],
    "suggested_first_checks": ["string"]
}
"""

            response = deploy_client.predict(
                endpoint=SCREENSHOT_MODEL,
                inputs={
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": ocr_prompt},
                                {
                                    "type": "image_url",
                                    "image_url": {"url": f"data:{mime_type};base64,{encoded}"},
                                },
                            ],
                        }
                    ]
                },
            )

            extracted = extract_model_text(response).strip()
            triage = extract_json_object(extracted)

            if not triage:
                triage = {
                    "visible_text": extracted,
                    "product_area": "Unknown",
                    "ui_area": "Unknown",
                    "detected_symptom": "Screenshot text was extracted, but structured triage parsing failed.",
                    "error_codes": [],
                    "object_names": {},
                    "likely_topic": "general",
                    "likely_intent": "deep_troubleshooting",
                    "severity": "unknown",
                    "confidence": "low",
                    "missing_info": ["Structured screenshot triage JSON was not returned."],
                    "suggested_first_checks": ["Review the extracted visible text and ask for missing context."],
                }

            visible_text = str(triage.get("visible_text") or "").strip()

            if not visible_text or "OCR_FAILED_UNREADABLE_IMAGE" in visible_text:
                return (
                    f"ATTACHMENT_OCR_FAILED\n"
                    f"File: {file_name}\n"
                    "The screenshot was attached, but readable text could not be extracted. "
                    "Ask the user to paste the visible error text. Do not infer error codes."
                )

            return format_screenshot_triage(file_name, triage)

        except Exception as e:
            error_text = str(e)

            if "ENDPOINT_NOT_FOUND" in error_text or "serving-endpoints" in error_text:
                return (
                    f"ATTACHMENT_OCR_ERROR\n"
                    f"File: {file_name}\n"
                    "The screenshot OCR endpoint configured in SCREENSHOT_MODEL does not exist or is not accessible. "
                    "This is an app configuration issue, not the user's screenshot error. "
                    "Ask the user to paste the visible screenshot text."
                )

            return (
                f"ATTACHMENT_OCR_ERROR\n"
                f"File: {file_name}\n"
                "The screenshot could not be processed by the OCR model. "
                "Ask the user to paste the visible error text. Do not infer error codes."
            )

    return (
        f"ATTACHMENT_UNSUPPORTED_TYPE\n"
        f"File: {file_name}\n"
        "This file type is not currently parsed."
    )
