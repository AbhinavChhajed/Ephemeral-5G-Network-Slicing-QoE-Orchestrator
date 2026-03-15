"""
LangGraph Agent Workflow for 5G Network Slicing Orchestrator
===========================================================
Multi-agent system for autonomous orchestration decisions:
- Telemetry Analyst: Analyzes network metrics and calculates QoE
- Slice Manager: Makes CREATE/MODIFY/DESTROY decisions
- Executor: Applies decisions to the network
"""

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional, TypedDict
from datetime import datetime
import uuid

from langgraph.graph import StateGraph, END, START
from langgraph.graph.state import CompiledStateGraph

from .prompts import (
    get_telemetry_analyst_prompt,
    get_slice_manager_prompt,
    TELEMETRY_ANALYST_TASK,
    SLICE_MANAGER_TASK,
)
from . import tools

LOG = logging.getLogger(__name__)

# Initialize LLM (using local Ollama or OpenAI)
try:
    from langchain.chat_models import ChatOllama
    LLM_MODEL = ChatOllama(
        base_url="http://localhost:11434",
        model="mistral",  # Use available local model
        temperature=0.1,  # Low temperature for consistent decisions
    )
    LOG.info("Initialized Ollama LLM (mistral)")
except Exception as e:
    LOG.warning(f"Ollama not available, attempting OpenAI: {str(e)}")
    try:
        from langchain.chat_models import ChatOpenAI
        LLM_MODEL = ChatOpenAI(
            model="gpt-4",
            temperature=0.1,
            api_key="your-api-key-here"  # Should be in environment
        )
        LOG.info("Initialized OpenAI LLM (gpt-4)")
    except Exception as e:
        LOG.error(f"No LLM available: {str(e)}")
        LLM_MODEL = None


# ============================================================================
# State Definition
# ============================================================================

class OrchestratorState(TypedDict):
    """State container for the orchestration workflow."""
    # Execution tracking
    execution_id: str
    timestamp: datetime
    cycle_number: int
    
    # Network data
    telemetry_snapshot: Dict[str, Any]
    active_slices: List[Dict[str, Any]]
    
    # Agent outputs
    analyst_assessment: Optional[Dict[str, Any]]
    orchestrator_decisions: Optional[Dict[str, Any]]
    
    # Execution results
    execution_results: List[Dict[str, Any]]
    
    # Logging and monitoring
    execution_log: List[str]
    errors: List[str]
    
    # Control flow
    requires_rescheduling: bool
    next_check_time: Optional[datetime]


# ============================================================================
# Node Functions
# ============================================================================

async def fetch_telemetry_node(state: OrchestratorState) -> OrchestratorState:
    """
    Fetch current network telemetry and active slices.
    
    Args:
        state: Current orchestration state
        
    Returns:
        Updated state with telemetry data
    """
    LOG.info(f"[Cycle {state['cycle_number']}] Fetching telemetry...")
    
    try:
        # Fetch latest telemetry snapshot
        telemetry = await tools.get_latest_telemetry()
        state["telemetry_snapshot"] = telemetry
        
        # Fetch all active slices
        slices = await tools.list_all_slices()
        state["active_slices"] = slices
        
        log_msg = f"Fetched telemetry: {len(slices)} active slices, " \
                  f"{len(telemetry.get('slices', {}))} metrics"
        state["execution_log"].append(log_msg)
        LOG.info(f"[Cycle {state['cycle_number']}] {log_msg}")
        
    except tools.BackendAPIError as e:
        error_msg = f"Telemetry fetch failed: {str(e)}"
        state["execution_log"].append(f"ERROR: {error_msg}")
        state["errors"].append(error_msg)
        LOG.error(f"[Cycle {state['cycle_number']}] {error_msg}")
    
    return state


async def telemetry_analyst_node(state: OrchestratorState) -> OrchestratorState:
    """
    Telemetry Analyst Agent: Analyze network metrics and calculate QoE.
    
    Uses LLM to process telemetry data and provide assessment.
    Falls back to heuristic analysis if LLM unavailable.
    
    Args:
        state: Current orchestration state with telemetry
        
    Returns:
        Updated state with analyst assessment
    """
    LOG.info(f"[Cycle {state['cycle_number']}] Telemetry Analyst processing...")
    
    try:
        # Prepare context
        telemetry_json = json.dumps(state["telemetry_snapshot"], indent=2, default=str)
        slices_json = json.dumps(state["active_slices"], indent=2, default=str)
        
        # Format user message
        user_message = TELEMETRY_ANALYST_TASK.format(
            telemetry_data=telemetry_json,
            active_slices=slices_json
        )
        
        if LLM_MODEL:
            # Use LLM for analysis
            LOG.debug(f"Invoking LLM for telemetry analysis...")
            response = await asyncio.to_thread(
                LLM_MODEL.invoke,
                [
                    {"role": "system", "content": get_telemetry_analyst_prompt()},
                    {"role": "user", "content": user_message}
                ]
            )
            response_text = response.content
            
            # Parse JSON response
            try:
                assessment = json.loads(response_text)
            except json.JSONDecodeError:
                # Try to extract JSON from response
                start = response_text.find('{')
                end = response_text.rfind('}') + 1
                if start != -1 and end > start:
                    assessment = json.loads(response_text[start:end])
                else:
                    raise ValueError("Could not parse LLM response")
            
        else:
            # Heuristic analysis
            LOG.warning("Using heuristic analysis (LLM unavailable)")
            assessment = await heuristic_telemetry_analysis(state)
        
        state["analyst_assessment"] = assessment
        
        log_msg = f"Analyst completed: {len(assessment.get('slices_status', []))} " \
                  f"slices analyzed, health={assessment.get('network_summary', {}).get('overall_health')}"
        state["execution_log"].append(log_msg)
        LOG.info(f"[Cycle {state['cycle_number']}] {log_msg}")
        
    except Exception as e:
        error_msg = f"Telemetry analysis failed: {str(e)}"
        state["execution_log"].append(f"ERROR: {error_msg}")
        state["errors"].append(error_msg)
        LOG.error(f"[Cycle {state['cycle_number']}] {error_msg}")
        state["analyst_assessment"] = {
            "analysis": "Analysis failed",
            "slices_status": [],
            "network_summary": {"overall_health": "unknown"}
        }
    
    return state


async def slice_manager_node(state: OrchestratorState) -> OrchestratorState:
    """
    Slice Manager Agent: Make orchestration decisions based on analysis.
    
    Evaluates QoE scores and decides on CREATE/MODIFY/DESTROY actions.
    Uses LLM for decision-making or heuristic rules if LLM unavailable.
    
    Args:
        state: Current state with analyst assessment
        
    Returns:
        Updated state with orchestration decisions
    """
    LOG.info(f"[Cycle {state['cycle_number']}] Slice Manager processing...")
    
    try:
        # Get network capacity
        system_status = await tools.get_system_status()
        total_slices = system_status.get("slices", {}).get("total", 0)
        active_slices = system_status.get("slices", {}).get("active", 0)
        
        capacity_status = {
            "total_slices": total_slices,
            "active_slices": active_slices,
            "available_capacity": 254 - total_slices,
            "max_slices": 254
        }
        
        # Format user message
        analyst_json = json.dumps(state["analyst_assessment"], indent=2, default=str)
        slices_json = json.dumps(state["active_slices"], indent=2, default=str)
        capacity_json = json.dumps(capacity_status, indent=2)
        
        user_message = SLICE_MANAGER_TASK.format(
            analyst_assessment=analyst_json,
            active_slices=slices_json,
            capacity_status=capacity_json,
            recent_events="[]"  # TODO: track recent events
        )
        
        if LLM_MODEL:
            # Use LLM for decisions
            LOG.debug(f"Invoking LLM for slice management...")
            response = await asyncio.to_thread(
                LLM_MODEL.invoke,
                [
                    {"role": "system", "content": get_slice_manager_prompt()},
                    {"role": "user", "content": user_message}
                ]
            )
            response_text = response.content
            
            # Parse JSON response
            try:
                decisions = json.loads(response_text)
            except json.JSONDecodeError:
                start = response_text.find('{')
                end = response_text.rfind('}') + 1
                if start != -1 and end > start:
                    decisions = json.loads(response_text[start:end])
                else:
                    raise ValueError("Could not parse LLM response")
        
        else:
            # Heuristic decisions
            LOG.warning("Using heuristic decisions (LLM unavailable)")
            decisions = await heuristic_slice_management(state)
        
        state["orchestrator_decisions"] = decisions
        
        decision_count = len(decisions.get("decisions", []))
        log_msg = f"Manager completed: {decision_count} decisions made"
        state["execution_log"].append(log_msg)
        LOG.info(f"[Cycle {state['cycle_number']}] {log_msg}")
        
    except Exception as e:
        error_msg = f"Slice management failed: {str(e)}"
        state["execution_log"].append(f"ERROR: {error_msg}")
        state["errors"].append(error_msg)
        LOG.error(f"[Cycle {state['cycle_number']}] {error_msg}")
        state["orchestrator_decisions"] = {"decisions": []}
    
    return state


async def executor_node(state: OrchestratorState) -> OrchestratorState:
    """
    Executor: Apply orchestration decisions to the network.
    
    Executes CREATE, MODIFY, and DESTROY actions via FastAPI backend.
    Tracks results and updates execution log.
    
    Args:
        state: Current state with decisions
        
    Returns:
        Updated state with execution results
    """
    LOG.info(f"[Cycle {state['cycle_number']}] Executor processing...")
    
    results = []
    decisions = state.get("orchestrator_decisions", {}).get("decisions", [])
    
    for decision in decisions:
        action = decision.get("action", "NO_ACTION")
        
        if action == "NO_ACTION":
            continue
        
        try:
            result = {
                "action": action,
                "status": "pending",
                "timestamp": datetime.utcnow().isoformat()
            }
            
            if action == "CREATE":
                # Create new slice
                response = await tools.create_slice(
                    slice_name=decision["slice_name"],
                    slice_type=decision.get("slice_type", "custom"),
                    priority=decision["priority"],
                    bandwidth_mbps=decision["bandwidth_mbps"],
                    delay_ms=decision["delay_ms"],
                    loss_percent=decision["loss_percent"],
                    duration_minutes=decision.get("duration_minutes"),
                )
                result["slice_id"] = response.get("slice_id")
                result["status"] = "success"
                log_msg = f"Created slice: {decision['slice_name']} (ID: {result['slice_id']})"
                
            elif action == "MODIFY":
                # Modify existing slice
                response = await tools.modify_slice(
                    slice_id=decision["target_slice_id"],
                    slice_name=decision.get("slice_name"),
                    priority=decision.get("priority"),
                    bandwidth_mbps=decision.get("bandwidth_mbps"),
                    delay_ms=decision.get("delay_ms"),
                    loss_percent=decision.get("loss_percent"),
                )
                result["slice_id"] = decision["target_slice_id"]
                result["status"] = "success"
                log_msg = f"Modified slice {decision['target_slice_id']}"
                
            elif action == "DESTROY":
                # Delete slice
                response = await tools.delete_slice(decision["target_slice_id"])
                result["slice_id"] = decision["target_slice_id"]
                result["status"] = "success"
                log_msg = f"Destroyed slice {decision['target_slice_id']}"
            
            results.append(result)
            state["execution_log"].append(log_msg)
            LOG.info(f"[Cycle {state['cycle_number']}] {log_msg}")
            
        except tools.BackendAPIError as e:
            result["status"] = "failed"
            result["error"] = str(e)
            results.append(result)
            error_msg = f"Failed to execute {action}: {str(e)}"
            state["execution_log"].append(f"ERROR: {error_msg}")
            state["errors"].append(error_msg)
            LOG.error(f"[Cycle {state['cycle_number']}] {error_msg}")
    
    state["execution_results"] = results
    LOG.info(f"[Cycle {state['cycle_number']}] Executor: {len(results)} decisions executed")
    
    return state


# ============================================================================
# Heuristic Fallbacks (when LLM unavailable)
# ============================================================================

async def heuristic_telemetry_analysis(state: OrchestratorState) -> Dict[str, Any]:
    """
    Heuristic telemetry analysis when LLM is unavailable.
    
    Based on simple rules and thresholds.
    """
    slices_status = []
    critical_alerts = []
    
    for slice_data in state["active_slices"]:
        slice_id = slice_data.get("slice_id")
        slice_type = slice_data.get("slice_type", "iot")
        
        try:
            qoe = await tools.get_qoe_score(slice_id, slice_type)
            score = qoe.get("score", 50)
            
            if score >= 80:
                status = "excellent"
            elif score >= 60:
                status = "good"
            elif score >= 40:
                status = "fair"
            else:
                status = "poor"
                critical_alerts.append(f"Slice {slice_id}: QoE {score}")
            
            slices_status.append({
                "slice_id": slice_id,
                "slice_name": slice_data.get("slice_name"),
                "slice_type": slice_type,
                "qoe_score": score,
                "status": status,
                "health_trend": "stable",
                "recommendations": qoe.get("recommendations", [])
            })
        except Exception as e:
            LOG.warning(f"Could not analyze slice {slice_id}: {str(e)}")
    
    return {
        "analysis": "Heuristic analysis (LLM unavailable)",
        "slices_status": slices_status,
        "network_summary": {
            "overall_health": "healthy" if not critical_alerts else "degraded",
            "slices_in_trouble": [s["slice_id"] for s in slices_status if s["status"] == "poor"],
            "critical_alerts": critical_alerts
        }
    }


async def heuristic_slice_management(state: OrchestratorState) -> Dict[str, Any]:
    """
    Heuristic slice management when LLM is unavailable.
    
    Based on simple QoE thresholds and rules.
    """
    decisions = []
    analyst_assessment = state.get("analyst_assessment", {})
    
    # Check each slice's status
    for slice_status in analyst_assessment.get("slices_status", []):
        slice_id = slice_status.get("slice_id")
        qoe_score = slice_status.get("qoe_score", 50)
        
        # If QoE is poor, consider modification
        if qoe_score < 40:
            decisions.append({
                "action": "MODIFY",
                "target_slice_id": slice_id,
                "bandwidth_mbps": slice_status.get("bandwidth_mbps", 50) * 1.2,
                "rationale": f"QoE {qoe_score} below threshold; increasing bandwidth",
                "confidence": 0.7
            })
    
    return {
        "reasoning": "Heuristic management (LLM unavailable)",
        "decisions": decisions,
        "execution_plan": f"Execute {len(decisions)} modifications",
        "risk_assessment": "Low risk; incremental bandwidth increases"
    }


# ============================================================================
# Graph Construction
# ============================================================================

def create_orchestrator_graph() -> CompiledStateGraph:
    """
    Create the LangGraph state graph for orchestration.
    
    Returns:
        Compiled state graph ready for execution
    """
    workflow = StateGraph(OrchestratorState)
    
    # Add nodes
    workflow.add_node("fetch_telemetry", fetch_telemetry_node)
    workflow.add_node("analyst", telemetry_analyst_node)
    workflow.add_node("manager", slice_manager_node)
    workflow.add_node("executor", executor_node)
    
    # Define edges
    workflow.add_edge(START, "fetch_telemetry")
    workflow.add_edge("fetch_telemetry", "analyst")
    workflow.add_edge("analyst", "manager")
    workflow.add_edge("manager", "executor")
    workflow.add_edge("executor", END)
    
    # Compile graph
    graph = workflow.compile()
    
    LOG.info("Orchestrator graph compiled successfully")
    return graph


# ============================================================================
# Main Orchestrator Function
# ============================================================================

async def run_orchestration_cycle(cycle_number: int = 1) -> Dict[str, Any]:
    """
    Run a single orchestration cycle.
    
    Executes the complete workflow:
    1. Fetch telemetry
    2. Analyze with Telemetry Analyst
    3. Make decisions with Slice Manager
    4. Execute with Executor
    
    Args:
        cycle_number: Cycle number for logging
        
    Returns:
        Final state with all results
    """
    LOG.info(f"\n{'='*60}")
    LOG.info(f"Starting Orchestration Cycle {cycle_number}")
    LOG.info(f"{'='*60}\n")
    
    # Initialize state
    initial_state: OrchestratorState = {
        "execution_id": str(uuid.uuid4()),
        "timestamp": datetime.utcnow(),
        "cycle_number": cycle_number,
        "telemetry_snapshot": {},
        "active_slices": [],
        "analyst_assessment": None,
        "orchestrator_decisions": None,
        "execution_results": [],
        "execution_log": [],
        "errors": [],
        "requires_rescheduling": False,
        "next_check_time": None,
    }
    
    try:
        # Create and execute graph
        graph = create_orchestrator_graph()
        final_state = await asyncio.to_thread(
            graph.invoke,
            initial_state
        )
        
        # Log cycle completion
        success_count = len([r for r in final_state.get("execution_results", []) 
                           if r.get("status") == "success"])
        error_count = len(final_state.get("errors", []))
        
        LOG.info(f"\n{'='*60}")
        LOG.info(f"Cycle {cycle_number} Complete")
        LOG.info(f"Results: {success_count} successful, {error_count} errors")
        LOG.info(f"{'='*60}\n")
        
        return final_state
        
    except Exception as e:
        LOG.error(f"Orchestration cycle {cycle_number} failed: {str(e)}")
        initial_state["errors"].append(f"Cycle execution failed: {str(e)}")
        return initial_state


async def start_continuous_orchestration(
    interval_seconds: int = 30,
    max_cycles: Optional[int] = None
) -> None:
    """
    Start continuous orchestration loop.
    
    Runs orchestration cycles at regular intervals.
    
    Args:
        interval_seconds: Seconds between cycles
        max_cycles: Optional maximum cycles before stopping
    """
    LOG.info(f"\n*** Starting 5G Network Slicing Orchestrator ***")
    LOG.info(f"Interval: {interval_seconds}s, Max cycles: {max_cycles or 'unlimited'}\n")
    
    cycle_number = 0
    
    try:
        while max_cycles is None or cycle_number < max_cycles:
            cycle_number += 1
            
            try:
                # Run orchestration cycle
                result = await run_orchestration_cycle(cycle_number)
                
                # Log summary
                errors = result.get("errors", [])
                if errors:
                    LOG.warning(f"Cycle {cycle_number} had {len(errors)} errors:")
                    for error in errors:
                        LOG.warning(f"  - {error}")
                
            except Exception as e:
                LOG.error(f"Error in cycle {cycle_number}: {str(e)}")
            
            # Wait for next cycle
            if max_cycles is None or cycle_number < max_cycles:
                LOG.info(f"Waiting {interval_seconds}s until next cycle...\n")
                await asyncio.sleep(interval_seconds)
        
        LOG.info(f"\n*** Orchestrator completed {max_cycles} cycles ***")
        
    except KeyboardInterrupt:
        LOG.info(f"\n*** Orchestrator stopped by user after {cycle_number} cycles ***")
    except Exception as e:
        LOG.error(f"Orchestrator error: {str(e)}")


# ============================================================================
# Entry Point
# ============================================================================

if __name__ == "__main__":
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Run continuous orchestration
    # Usage: python -m orchestrator.agent_workflow
    asyncio.run(start_continuous_orchestration(interval_seconds=30, max_cycles=None))
