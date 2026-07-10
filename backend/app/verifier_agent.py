from app.render_client import render_template
from app.visual_diff import screenshot_html, compute_ssim
from app.critic import run_critic, mismatches_to_correction_notes
import logging

logger = logging.getLogger("documirror.verifier")

def verifier_node(state: dict):
    """
    1. Renders draft HTML to an image.
    2. Compares against the source image/PDF page (SSIM).
    3. If SSIM < 0.95, runs critic to list mismatches.
    Increments iterations and returns mismatches + SSIM.
    """
    iterations = state.get("iterations", 0)
    draft_html = state.get("draft_html", "")
    image_bytes = state.get("image_bytes")
    raw_fields = state.get("raw_fields", {})
    iterations_history = state.get("iterations_history", [])
    
    screenshot_bytes = b""
    ssim_score = 0.0
    mismatches = []
    
    if draft_html and image_bytes:
        try:
            # 1. Render template to HTML
            # Note: draft_html is actually an EJS template string at this point
            # We need to compile it via the render service
            final_html = render_template(draft_html, raw_fields)
            
            # 2. Screenshot the rendered HTML
            screenshot_bytes = screenshot_html(final_html)
            
            # 3. Compute SSIM
            ssim_score = compute_ssim(image_bytes, screenshot_bytes)
            logger.info(f"Iteration {iterations+1} SSIM: {ssim_score}")
            
            # 4. If SSIM is low, run critic
            if ssim_score < 0.95:
                critic_res = run_critic(image_bytes, screenshot_bytes)
                if critic_res.mismatches:
                    # Convert to string list for state compatibility
                    # We can use mismatches_to_correction_notes directly or just list them
                    # We will store the notes in state.mismatches for the generator
                    notes = mismatches_to_correction_notes(critic_res)
                    if notes:
                        mismatches = [notes]
                        
        except Exception as e:
            logger.error(f"Verification failed: {e}")
            mismatches = [f"Verification loop encountered an error: {e}"]
    else:
        logger.warning("No draft_html or image_bytes to verify.")

    iterations_history.append({
        "ssim_score": ssim_score,
        "mismatch_count": len(mismatches)
    })
        
    return {
        "screenshot_bytes": screenshot_bytes,
        "mismatches": mismatches,
        "iterations": iterations + 1,
        "iterations_history": iterations_history,
        "status": "verified"
    }
