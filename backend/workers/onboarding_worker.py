import os
import tempfile
from app.channels import onboarding
from app.channels import youtube_importer
from app.channels import reference_analyzer
from app.services.supabase_client import get_client

def run_existing_channel_onboarding(channel_id: str, youtube_channel_id: str, youtube_api_key: str) -> None:
    try:
        print(f"[OnboardingWorker] Starting onboarding for existing channel {channel_id}")
        
        # a. update_onboarding_status(channel_id, "scanning")
        print(f"[OnboardingWorker] Updating status to 'scanning'")
        onboarding.update_onboarding_status(channel_id, "scanning")
        
        # b. Fetch all shorts
        print(f"[OnboardingWorker] Fetching shorts from YouTube channel {youtube_channel_id}")
        shorts = youtube_importer.get_channel_shorts(youtube_channel_id, youtube_api_key)
        
        # c. If no shorts found: update status to "ready", return
        if not shorts:
            print(f"[OnboardingWorker] No shorts found for channel {channel_id}. Setting to 'ready'")
            onboarding.update_onboarding_status(channel_id, "ready")
            return
            
        # d. update_onboarding_status(channel_id, "analyzing")
        print(f"[OnboardingWorker] Found {len(shorts)} shorts. Updating status to 'analyzing'")
        onboarding.update_onboarding_status(channel_id, "analyzing")
        
        # e. Identify successful
        print(f"[OnboardingWorker] Identifying successful shorts")
        successful = youtube_importer.identify_successful_shorts(shorts)
        
        if not successful:
            print(f"[OnboardingWorker] No successful shorts identified. Setting to 'ready'")
            onboarding.update_onboarding_status(channel_id, "ready")
            return
            
        # f. Analyze top 20
        top_successful = successful[:20]
        print(f"[OnboardingWorker] Analyzing top {len(top_successful)} successful shorts")
        reference_analyzer.analyze_channel_history(channel_id, top_successful)
        
        # g. Build DNA
        print(f"[OnboardingWorker] Building channel DNA")
        dna = reference_analyzer.build_channel_dna(channel_id)
        
        # h. If DNA built: set DNA, else update status to ready with empty DNA
        if dna:
            print(f"[OnboardingWorker] DNA built successfully. Saving DNA")
            onboarding.set_channel_dna(channel_id, dna)
        else:
            print(f"[OnboardingWorker] DNA building returned empty. Saving empty DNA")
            onboarding.set_channel_dna(channel_id, {})
            
        print(f"[OnboardingWorker] Onboarding completed for {channel_id}")
        
    except Exception as e:
        print(f"[OnboardingWorker] Error during existing channel onboarding for {channel_id}: {e}")
        try:
            onboarding.update_onboarding_status(channel_id, "ready")
        except Exception as inner_e:
            print(f"[OnboardingWorker] Failed to set fallback status for {channel_id}: {inner_e}")

def run_new_channel_onboarding(channel_id: str, reference_clip_paths: list[str] | None = None) -> None:
    try:
        print(f"[OnboardingWorker] Starting onboarding for new channel {channel_id}")
        
        # a. update_onboarding_status(channel_id, "analyzing")
        print(f"[OnboardingWorker] Updating status to 'analyzing'")
        onboarding.update_onboarding_status(channel_id, "analyzing")
        
        # b. If reference_clip_paths provided
        if reference_clip_paths:
            print(f"[OnboardingWorker] Analyzing {len(reference_clip_paths)} reference clips")
            for path in reference_clip_paths:
                try:
                    reference_analyzer.analyze_single_clip(path, channel_id, source="external_reference")
                except Exception as clip_e:
                    print(f"[OnboardingWorker] Error analyzing reference clip {path}: {clip_e}")
                    # Continue analyzing other clips even if one fails
        else:
            print(f"[OnboardingWorker] No reference clips provided for {channel_id}")
            
        # c. Try to build DNA from reference clips
        print(f"[OnboardingWorker] Attempting to build channel DNA")
        dna = reference_analyzer.build_channel_dna(channel_id)
        
        # d. If DNA built: set DNA, else update status to ready with empty DNA
        if dna:
            print(f"[OnboardingWorker] DNA built successfully. Saving DNA")
            onboarding.set_channel_dna(channel_id, dna)
        else:
            print(f"[OnboardingWorker] No DNA built. Setting empty DNA")
            onboarding.set_channel_dna(channel_id, {})
            
        print(f"[OnboardingWorker] Onboarding completed for {channel_id}")
        
    except Exception as e:
        print(f"[OnboardingWorker] Error during new channel onboarding for {channel_id}: {e}")
        try:
            onboarding.update_onboarding_status(channel_id, "ready")
        except Exception as inner_e:
            print(f"[OnboardingWorker] Failed to set fallback status for {channel_id}: {inner_e}")
