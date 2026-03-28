def build_metadata_analysis_prompt(
    channel_context: str,
    video_title: str,
    video_channel: str,
    video_duration_minutes: float,
    video_view_count: int,
    video_published_at: str,
    video_description: str,
    top_comments: str
) -> str:
    """
    Transkript olmadığında metadata + yorumlardan analiz için Gemini prompt'u.

    Args:
        channel_context: Channel DNA bağlam metni
        video_title: Video başlığı
        video_channel: Kaynak kanal adı
        video_duration_minutes: Video süresi (dakika)
        video_view_count: Görüntülenme sayısı
        video_published_at: Yayın tarihi
        video_description: Video açıklaması
        top_comments: En iyi yorumlar (metin olarak)

    Returns:
        Gemini'ye gönderilecek prompt string
    """
    raise NotImplementedError("TODO")
