def build_query_generation_prompt(
    channel_context: str,
    recent_successes: str,
    weak_queries: str,
    trending_topics: str,
    query_count: int
) -> str:
    """
    F01 Query Generation için Gemini prompt'unu oluşturur.

    Args:
        channel_context: Channel DNA'dan oluşturulan bağlam metni
        recent_successes: Son başarılı kaynakların listesi
        weak_queries: Geçmişte zayıf sonuç veren sorgular
        trending_topics: Güncel trendler (varsa)
        query_count: Üretilecek sorgu sayısı

    Returns:
        Gemini'ye gönderilecek prompt string
    """
    raise NotImplementedError("TODO")
