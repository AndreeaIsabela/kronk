import re
import discord


def parse_mentions(players_str: str, guild: discord.Guild) -> list[tuple[str, str]]:
    """Extract (user_id, display_name) pairs from a string of @mentions."""
    ids = re.findall(r"<@!?(\d+)>", players_str)
    targets = []
    for uid in ids:
        member = guild.get_member(int(uid))
        name = member.display_name if member else f"User {uid}"
        targets.append((uid, name))
    return targets
