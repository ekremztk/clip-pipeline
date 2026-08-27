-- Rebuild TheYellow Cast around gender-neutral human stories and Craig Ferguson chemistry.

UPDATE channels
SET
    niche = 'Craig Ferguson host-guest chemistry and human celebrity stories',
    content_format = 'talk_show_interview_shorts',
    channel_vision = 'famous people stop performing and become funny, flawed, ordinary humans with Craig Ferguson',
    channel_dna = $dna${
        "tone": "warm, funny, human, playful, quick, and unpredictable. The guest should feel like a likeable, unpolished person rather than a polished celebrity. Craig's reactions and timing matter, but the guest must remain essential. Never sexualised, appearance-led, cruel, or tabloid.",
        "do_list": [
            "Family and relationships: parents, children, siblings, partners, relatives, parenting failures, or family members embarrassing the guest. Prefer a clear scene and payoff.",
            "Childhood and life before fame: school, first jobs, early ambitions, childhood crushes, bad decisions, and formative humiliation.",
            "Self-deprecating embarrassment: the guest is clumsy, wrong, caught out, overconfident, defeated, or plainly the fool and can laugh about it.",
            "Craig teasing or roasting the guest and the guest reacting well, firing back, reversing the status, or making Craig lose control because of wit rather than appearance.",
            "Small ordinary opinions, personal rules, habits, obsessions, accents, verbal tics, fears, or quirks delivered with conviction.",
            "Being unrecognised, treated as a normal person, doing something unglamorous, or failing at an ordinary task.",
            "Animals and pets causing chaos or revealing something funny about the guest.",
            "Unexpected honesty or vulnerability that remains self-contained and watchable rather than becoming a context-heavy serious discussion.",
            "The interview genuinely derailing: role reversal, mutual improvisation, escalating absurdity, or a guest-specific running bit that could not happen with just anyone.",
            "An encounter with another recognisable person when the story reveals character and has a complete payoff.",
            "The clip must be understandable to a stranger within the first two seconds and contain one complete story, exchange, or escalation with a clean payoff."
        ],
        "keyterms": [
            "mum",
            "mom",
            "dad",
            "mother",
            "father",
            "son",
            "daughter",
            "brother",
            "sister",
            "wife",
            "husband",
            "girlfriend",
            "boyfriend",
            "dog",
            "cat",
            "embarrassing",
            "mortified",
            "recognised",
            "recognized",
            "when I was a kid",
            "growing up",
            "at school",
            "childhood",
            "my first job",
            "Craig",
            "Geoff Peterson",
            "awkward pause"
        ],
        "dont_list": [
            "Anything selected mainly because of the guest's body, clothing, attractiveness, wardrobe, or Craig complimenting their appearance.",
            "Flirtation, sexual tension, physical proximity, or a double meaning when that is the entire substance of the clip. Innuendo may be incidental inside a stronger human story, but it is never sufficient by itself.",
            "Promotion: a film, album, tour, book, brand, plot summary, or career recap unless it immediately becomes a strong personal story.",
            "Fame stories about awards, paparazzi, red carpets, being mobbed by fans, or the burden of celebrity unless the point is being treated as an ordinary person.",
            "Moments where Craig supplies nearly all of the entertainment and the guest contributes no story, reaction, reversal, or distinctive personality.",
            "Generic banter, compliments, greetings, or show rituals that would work the same way with any guest.",
            "Inside jokes or callbacks that require another appearance or the rest of the episode to understand.",
            "Cruel humiliation, hostility without warmth, or humour that makes the guest visibly withdraw.",
            "Multiple overlapping versions of the same moment. Keep only the strongest complete cut.",
            "Starting mid-word or mid-thought, or ending on a new unfinished sentence after the payoff."
        ],
        "hook_style": "the guest beginning a clear personal story, admitting something embarrassing or unexpectedly honest, stating a strange ordinary opinion, or immediately answering a short Craig setup in a way that changes the interaction. Never use an appearance compliment or unexplained innuendo as the hook.",
        "no_go_zones": [
            "explicit sexual detail",
            "graphic tragedy or trauma",
            "active legal allegations",
            "medical or mental health speculation",
            "sexual content involving minors",
            "appearance-led sexualisation"
        ],
        "prompt_text": "YOU ARE EDITING FOR:\nPeople who come for the person and the interaction, not the promotion. The source is The Late Late Show with Craig Ferguson, but this is not a channel about Craig flirting with guests. It is a channel about famous men and women dropping their polished celebrity persona and becoming funny, flawed, ordinary humans while Craig gives them room to play.\n\nThe viewer may recognise the guest but does not care what they are promoting. Select without gender bias. A male and female guest are judged by exactly the same standard: the strength, clarity and payoff of the moment.\n\nCORE PRINCIPLE:\nThe substance comes first; Craig chemistry comes second. First find a personal story, revealing reaction, ordinary opinion, embarrassment, vulnerability, quirk, roast, or genuinely surprising exchange. Then prefer the version where Craig's listening, timing, teasing, loss of control, or improvisation makes that substance better. Chemistry can elevate a moment; it cannot replace substance.\n\nTONE: warm, funny, human, playful, quick and unpredictable. The guest should feel like a likeable, unpolished person rather than an impressive celebrity. Genuine laughter is a strong signal. Warm teasing is welcome when the guest plays back. Never sexualised, appearance-led, cruel or tabloid.\n\nWHAT THIS AUDIENCE REWARDS, roughly in order (content_type in brackets):\n  1. Family and relationships: parents, children, siblings, partners or relatives embarrassing the guest, or the guest embarrassing them. [family_story]\n  2. Childhood and life before fame: school, first jobs, early ambitions, childhood crushes, bad decisions and early humiliation. [childhood_memory]\n  3. Self-deprecation: the guest is clumsy, wrong, caught out, overconfident, defeated or clearly the fool. [self_deprecating_embarrassment]\n  4. Craig or another person teasing the guest, followed by a real reaction, comeback or status reversal. [guest_is_teased]\n  5. A small ordinary opinion, personal rule or mundane conviction delivered as if it matters enormously. [ordinary_opinion]\n  6. Not being recognised, being treated as normal, doing something unglamorous or failing at an ordinary task. [being_treated_as_normal]\n  7. A distinctive habit, obsession, fear, accent, verbal tic or quirk. [personal_quirk]\n  8. Animals or pets causing chaos or revealing character. [animal_story]\n  9. The guest saying something unexpectedly frank, honest or vulnerable. [unexpected_honesty]\n 10. A warm roast, disagreement or competitive exchange in which both people participate. [playful_roast_or_argument]\n 11. The guest's wit, answer or behaviour genuinely throwing Craig off — never their appearance alone. [host_thrown_off_by_guest]\n 12. The guest taking control, questioning Craig or reversing their roles. [role_reversal]\n 13. The planned interview collapsing into a guest-specific improvised exchange. [interview_derails]\n 14. Craig and the guest building an absurd premise together, with escalation and payoff. [shared_absurdity]\n 15. A running show bit becoming specific to this guest and producing a real payoff. [show_running_bit_with_guest_payoff]\n 16. An encounter with another person the audience recognises, when it reveals the guest's character. [encounter_with_a_famous_person]\n\nThese categories say where to look first, not what to reject. If the strongest moment fits none of them, select it and use [other], then explain the exact strength in reason. content_type must be exactly one bracketed tag above: lower case, underscores, no slashes, commas or description.\n\nHARD REJECTS:\n  - Anything selected mainly because of a guest's body, clothes, attractiveness, wardrobe, or Craig complimenting their appearance.\n  - Flirtation, sexual tension, physical proximity or a double meaning when that is the whole clip. Innuendo may occur incidentally inside a stronger human story, but it is never sufficient on its own.\n  - Promotion, plot explanation, career recap, awards, paparazzi, red carpets or generic fame talk. A personal story told during promotion is still eligible; judge the actual moment.\n  - Craig performing while the guest is merely present. The guest must contribute a story, reaction, reversal or distinctive personality.\n  - Generic greetings, compliments, banter or show rituals that would work identically with another guest.\n  - Context-dependent callbacks, cruel humiliation, hostility without warmth, or multiple versions of the same moment.\n\nFORBIDDEN TOPICS: explicit sexual detail; graphic depiction of real tragedy or trauma; active legal allegations against a living person; medical or mental health speculation; sexual content involving a minor; appearance-led sexualisation. Judge the substance, not isolated words.\n\nCLIP CONSTRUCTION:\n  - A stranger must understand the setup within two seconds.\n  - Prefer the guest starting a clear story or immediately answering a short Craig setup.\n  - Preserve enough of Craig's question or reaction to make the chemistry legible, but do not let him dominate the clip.\n  - One clip contains one story, exchange or escalation and one clean payoff.\n  - Do not start mid-word or mid-thought. Do not continue into a new unfinished topic after the payoff.\n  - When candidates overlap, keep only the strongest complete version.\n  - Duration is not a quality signal. Let the moment decide its length inside the job limits.\n\nFINAL TESTS:\n  1. If the guest were replaced by another celebrity, would the moment still work almost unchanged? If yes, it is generic and should usually be rejected.\n  2. If the sexual or appearance element were removed, is there still a story, character reveal or comic reversal? If no, reject it.\n  3. Does the guest become more human, specific or surprising by the end? If no, keep looking.\n",
        "title_style": "lowercase only. Start with the guest's full name, then describe the specific human story, embarrassment, opinion, reversal, or absurd situation in plain words. Promise the story without revealing the payoff. Keep it short and use one fitting emoji at the end. Examples: \"ryan reynolds rode the wrong bus for a childhood crush 😭\", \"kristen bell's family knew exactly how to embarrass her 😂\", \"stephen fry turned the interview around on craig 😳\". Never lead with appearance, flirting, sexual tension, generic chemistry, or formal press-tour language.",
        "description_template": "Write one compact English sentence. Start with the guest's name, then describe the specific personal story or Craig-guest exchange in plain language. Then add broad comedy and talk-show hashtags followed by person and topic tags. Pattern: [PERSON] shares/reveals [specific story or exchange] about [TOPIC], creating a funny and human Craig Ferguson interview moment. #comedy #funny #celebrityinterviews #talkshow #interview #celebrities #comedygold #comedyclips #craigferguson #[person] #[topic]",
        "best_content_types": [
            "family_story",
            "childhood_memory",
            "self_deprecating_embarrassment",
            "guest_is_teased",
            "ordinary_opinion",
            "being_treated_as_normal",
            "personal_quirk",
            "animal_story",
            "unexpected_honesty",
            "playful_roast_or_argument",
            "host_thrown_off_by_guest",
            "role_reversal",
            "interview_derails",
            "shared_absurdity",
            "show_running_bit_with_guest_payoff",
            "encounter_with_a_famous_person",
            "other"
        ],
        "humor_profile": {
            "style": "warm character comedy, self-deprecation, family chaos, ordinary convictions, friendly roasting, status reversal, improvised absurdity, and occasional sincere turns",
            "frequency": "frequent",
            "triggers": [
                "the guest embarrasses themselves",
                "a family member embarrasses the guest",
                "confidence collapses into failure",
                "Craig teases and the guest fires back",
                "the guest makes Craig genuinely lose control",
                "an ordinary opinion is delivered with absurd conviction",
                "both people build the same ridiculous premise",
                "a joke unexpectedly reveals something sincere",
                "genuine laughter after a clear payoff"
            ]
        },
        "sacred_topics": [
            "family and parenting",
            "childhood, school and life before fame",
            "self-inflicted embarrassment",
            "being teased and firing back",
            "ordinary life despite fame",
            "small strong opinions",
            "personal quirks and obsessions",
            "animals and pets",
            "unexpected honesty",
            "Craig and the guest changing the power dynamic"
        ],
        "audience_identity": "English-speaking viewers who enjoy famous men and women becoming funny, flawed, ordinary people in spontaneous Craig Ferguson conversations. They come for personality, personal stories and host-guest chemistry, not promotion, glamour, gender-specific attraction or celebrity status.",
        "speaker_preference": "guest-led with essential host-guest chemistry",
        "content_format": [
            "talk_show",
            "celebrity_interview",
            "host_guest_chemistry",
            "youtube_shorts"
        ],
        "target_platforms": [
            "youtube_shorts"
        ],
        "selection_note": "OtherSide Cast supplies the proven human-story rules; successful Speedy Cast material confirms that the same rules work for male guests through childhood humiliation, family and parenting stories, failed bravado, ordinary convictions, teasing and vulnerability. Craig Ferguson chemistry is an additional quality layer, not a replacement for substance. Select the single strongest moment regardless of guest gender."
    }$dna$::jsonb,
    updated_at = now()
WHERE id = 'theyellow_cast';
