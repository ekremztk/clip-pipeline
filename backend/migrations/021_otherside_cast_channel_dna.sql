-- Migration 021: Seed production Channel DNA for OtherSide Cast.

UPDATE channels
SET
    niche = 'female celebrity talk-show clips',
    content_format = 'talk_show_interview_shorts',
    channel_dna = $dna${
        "tone": "playful, sharp, celebrity-focused, fast-moving, emotionally readable, and lightly gossip-driven without becoming mean",
        "do_list": [
            "Prioritize female guest-dominant moments with a complete mini-story or clear punchline",
            "Open on an immediately understandable hook within the first 2 seconds",
            "Select awkward, embarrassing, chaotic, self-deprecating, flirty, surprising, or unusually honest celebrity stories",
            "Favor moments with visible reactions, laughter, facial expressions, or host/guest timing that can carry a Short visually",
            "Keep clips tight and understandable without needing the full interview",
            "Prefer US late-night talk-show energy: quick setup, clear story, payoff, reaction"
        ],
        "dont_list": [
            "Do not select pure album, movie, tour, fashion, or brand promo unless the moment contains a strong personal story or joke",
            "Do not select clips where the host dominates and the female guest is mostly reacting",
            "Do not select contextless fan-service, inside jokes, or references that require watching the full interview",
            "Do not select low-energy compliments, generic career recap, or polite press-tour answers",
            "Do not start mid-word, mid-thought, or on filler unless the filler is part of the hook",
            "Do not end after the payoff with a new unfinished sentence"
        ],
        "hook_style": "direct funny setup, awkward confession, unexpected celebrity admission, or visually obvious reaction",
        "no_go_zones": [
            "heavy politics",
            "explicit sexual detail",
            "graphic tragedy or trauma",
            "active legal allegations",
            "medical or mental health speculation",
            "sexualized framing of underage stories"
        ],
        "title_style": "lowercase only. Start with the main female celebrity name, then the funny, awkward, shocking, or chaotic situation. Keep it short, simple, and curiosity-driven. Use one fitting emoji at the end. Examples: \"jennifer lawrence lost it over this horse story 😭\", \"taylor swift's laser eye video was brutal 😭\", \"mila kunis' honeymoon went completely wrong 😭\". Avoid formal press-tour titles, uppercase, generic wording, and harsh/risky phrasing when a softer phrase works.",
        "description_template": "Write one compact English sentence. Start with the main person name, then explain the specific funny, awkward, surprising, or chaotic moment in plain language. Mention the context clearly without sounding corporate. After the sentence, add broad comedy/talk-show hashtags first, then person/topic/show-specific tags. Use this pattern: [PERSON] shares/reveals/explains [specific story] about [TOPIC/CONTEXT], creating a funny or memorable talk show moment. #comedy #funny #celebrityinterviews #talkshow #interview #celebrities #comedygold #comedyclips #[person] #[topic]",
        "best_content_types": [
            "funny_reaction",
            "awkward_story",
            "embarrassing_confession",
            "celebrity_reveal",
            "chaotic_personal_story",
            "relationship_or_family_anecdote",
            "unexpected_honesty"
        ],
        "humor_profile": {
            "style": "playful celebrity humor, self-deprecation, awkward honesty, deadpan reactions, and host-guest timing",
            "frequency": "frequent",
            "triggers": [
                "embarrassing personal detail",
                "unexpected honesty",
                "visible guest reaction",
                "host surprise",
                "celebrity acting unlike their public image",
                "story payoff followed by laughter"
            ]
        },
        "sacred_topics": [
            "female celebrity stories",
            "awkward talk-show moments",
            "unexpected confessions",
            "funny reactions",
            "relationship and family anecdotes",
            "behind-the-scenes celebrity chaos"
        ],
        "audience_identity": "English-speaking YouTube Shorts viewers who enjoy female celebrity talk-show moments, funny interviews, pop-culture stories, and quick celebrity personality clips",
        "speaker_preference": "guest_dominant",
        "duration_range": {
            "min": 12,
            "max": 55,
            "sweet_spot": "22-42"
        },
        "avg_successful_duration": 32,
        "content_format": [
            "talk_show",
            "celebrity_interview",
            "youtube_shorts"
        ],
        "target_platforms": [
            "youtube_shorts"
        ],
        "keyterms": [
            "funny",
            "awkward",
            "embarrassing",
            "confession",
            "celebrity",
            "talk show",
            "interview",
            "reaction",
            "story"
        ]
    }$dna$::jsonb,
    updated_at = now()
WHERE id = 'otherside_cast';
