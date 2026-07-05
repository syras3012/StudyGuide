# ruff: noqa
# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
import re
import json
import datetime
import sys

# IMPORTANT: config must be imported FIRST — it calls load_dotenv() and
# sets GOOGLE_GENAI_USE_VERTEXAI=False before any ADK framework code runs.
from .config import config  # noqa: E402

from google.adk.agents import LlmAgent
from google.adk.tools import AgentTool
from google.adk.workflow import Workflow, START
from google.adk.apps import App
from google.adk.events.event import Event
from google.adk.events.request_input import RequestInput
from google.adk.agents.context import Context
from google.genai import types

from google.adk.tools.mcp_tool import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StdioConnectionParams
from mcp import StdioServerParameters


# --- MCP TOOLSET CONFIGURATION ---

mcp_toolset = McpToolset(
    connection_params=StdioConnectionParams(
        server_params=StdioServerParameters(
            command="python",
            args=["-m", "app.mcp_server"]
        )
    )
)

# --- SUB-AGENTS ---

study_planner = LlmAgent(
    name="study_planner",
    model=config.model,
    description="Creates a customized study plan and schedule based on the user's goals and subject.",
    instruction=(
        "You are a study planner specialist. Analyze the student's learning goals, subject, timeline, "
        "and current level. Create a structured study plan with clear milestones, daily tasks, and "
        "recommended focus areas. Use the study notes and resources from the MCP tools to enrich the plan."
    ),
    tools=[mcp_toolset]
)

quiz_generator = LlmAgent(
    name="quiz_generator",
    model=config.model,
    description="Generates quiz questions and grades student answers for exam preparation.",
    instruction=(
        "You are a quiz and evaluation specialist. Generate multiple-choice or short-answer quiz questions "
        "about the requested topic. Assess the student's answers, grade them, and provide detailed "
        "explanations. When a quiz is finished, make sure to record the final quiz score using the "
        "record_quiz_score tool."
    ),
    tools=[mcp_toolset]
)

# --- ORCHESTRATOR ---

tutor_orchestrator = LlmAgent(
    name="tutor_orchestrator",
    model=config.model,
    instruction=(
        "You are StudyGuide AI, a personalized tutor and exam preparation agent. "
        "Your goal is to guide the student through their learning process. "
        "You can delegate planning to the 'study_planner' and quiz design to the 'quiz_generator' "
        "using their respective tools. Provide a cohesive, friendly, and structured tutoring experience."
    ),
    tools=[
        AgentTool(study_planner),
        AgentTool(quiz_generator)
    ]
)

# --- WORKFLOW NODE FUNCTIONS ---

def get_text(content: types.Content) -> str:
    """Helper to extract text from a Content object safely."""
    if hasattr(content, 'parts') and content.parts:
        return "".join([p.text for p in content.parts if p.text])
    if isinstance(content, str):
        return content
    return str(content)

# Pre-compiled regex for PII (email, phone number)
EMAIL_REGEX = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")
PHONE_REGEX = re.compile(r"\b\d{3}[-.]?\d{3}[-.]?\d{4}\b")

# Prompt injection keywords
INJECTION_KEYWORDS = [
    "ignore previous instructions",
    "system prompt",
    "override rules",
    "you are now a",
    "bypass restrictions"
]

# Academic integrity keywords (cheating check)
CHEATING_KEYWORDS = [
    "do my homework",
    "write my essay",
    "solve my exam",
    "cheat sheet",
    "give me the answers"
]

def security_checkpoint(ctx: Context, node_input: types.Content) -> Event:
    """Validates student inputs for safety, prompt injection, and PII."""
    raw_text = get_text(node_input)
    clean_text = raw_text
    
    pii_redacted = False
    injection_detected = False
    cheating_detected = False
    
    # 1. PII Redaction
    if config.pii_redaction_enabled:
        if EMAIL_REGEX.search(clean_text):
            clean_text = EMAIL_REGEX.sub("[REDACTED_EMAIL]", clean_text)
            pii_redacted = True
        if PHONE_REGEX.search(clean_text):
            clean_text = PHONE_REGEX.sub("[REDACTED_PHONE]", clean_text)
            pii_redacted = True

    # 2. Prompt Injection Detection
    if config.injection_detection_enabled:
        lower_text = clean_text.lower()
        if any(kw in lower_text for kw in INJECTION_KEYWORDS):
            injection_detected = True

    # 3. Domain-specific (Cheating/Academic Integrity) Check
    lower_text = clean_text.lower()
    if any(kw in lower_text for kw in CHEATING_KEYWORDS):
        cheating_detected = True

    # Determine Severity and Action
    if injection_detected or cheating_detected:
        severity = "CRITICAL"
        action = "BLOCK"
        route = "security_alert"
        output_data = "Safety Violation: Prompt injection or cheating attempt detected."
    elif pii_redacted:
        severity = "WARNING"
        action = "REDACT_AND_PASS"
        route = None
        output_data = clean_text
    else:
        severity = "INFO"
        action = "PASS"
        route = None
        output_data = clean_text

    # Write Structured JSON Audit Log
    log_entry = {
        "timestamp": datetime.datetime.utcnow().isoformat(),
        "session_id": ctx.session.id,
        "severity": severity,
        "action": action,
        "pii_redacted": pii_redacted,
        "injection_detected": injection_detected,
        "cheating_detected": cheating_detected,
        "input_preview": raw_text[:100] + "..." if len(raw_text) > 100 else raw_text
    }
    
    try:
        with open("security_audit.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry) + "\n")
    except Exception as e:
        print(f"Failed to write security log: {e}", file=sys.stderr)

    if route == "security_alert":
        return Event(output=output_data, route="security_alert")
        
    cleaned_content = types.Content(role='user', parts=[types.Part.from_text(text=clean_text)])
    return Event(output=cleaned_content)

def security_event(ctx: Context, node_input: str) -> Event:
    """Handles violations detected by the security checkpoint."""
    return Event(output="Security checkpoint alert: Request blocked due to safety violations (prompt injection or cheating attempt).")

async def hitl_review_node(ctx: Context, node_input: types.Content) -> Event:
    """Pauses the workflow for human input (RequestInput) on each tutoring cycle."""
    text_content = get_text(node_input)

    # Check if the tutor wants to end the session
    if "goodbye" in text_content.lower() or "session completed" in text_content.lower():
        yield Event(output=text_content, route="finish")
        return

    # Keep track of conversation turns to generate unique interrupt IDs
    turn = ctx.state.get("hitl_turn", 0) + 1
    ctx.state["hitl_turn"] = turn
    interrupt_id = f"user_message_{turn}"

    # If we haven't received input for this turn yet, pause execution
    if not ctx.resume_inputs or interrupt_id not in ctx.resume_inputs:
        yield RequestInput(
            interrupt_id=interrupt_id,
            message="Ask your tutor questions, confirm your study plan, or start a quiz."
        )
        return

    # Retrieve user's response and route back to orchestrator
    user_response = ctx.resume_inputs[interrupt_id]
    yield Event(output=user_response, route="continue")

def final_output(ctx: Context, node_input: str) -> Event:
    """Emits final output content for display in the Web UI."""
    yield Event(content=types.Content(role='model', parts=[types.Part.from_text(text=node_input)]))
    yield Event(output=node_input)

# --- WORKFLOW GRAPH CONFIGURATION ---

root_agent = Workflow(
    name="studyguide_workflow",
    edges=[
        ('START', security_checkpoint),
        (security_checkpoint, {
            '__DEFAULT__': tutor_orchestrator,
            'security_alert': security_event
        }),
        (tutor_orchestrator, hitl_review_node),
        (hitl_review_node, {
            'continue': tutor_orchestrator,
            'finish': final_output
        }),
        (security_event, final_output),
    ]
)

app = App(
    root_agent=root_agent,
    name="app",
)
