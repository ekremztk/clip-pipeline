def build_deep_analysis_prompt(
    channel_context: str,
    video_title: str,
    video_channel: str,
    video_duration_minutes: float,
    video_view_count: int,
    video_published_at: str,
    video_description: str,
    sampled_transcript: str
) -> str:
    """
    F05 Deep Analysis için Gemini prompt'unu oluşturur.

    Args:
        channel_context: Channel DNA bağlam metni
        video_title: Video başlığı
        video_channel: Kaynak kanal adı
        video_duration_minutes: Video süresi (dakika)
        video_view_count: Görüntülenme sayısı
        video_published_at: Yayın tarihi
        video_description: Video açıklaması (ilk 500 karakter)
        sampled_transcript: Örneklenmiş transkript

    Returns:
        Gemini'ye gönderilecek prompt string
    """
    raise NotImplementedError("TODO")
