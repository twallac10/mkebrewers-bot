"""World Series championship detection, shared by the summary script and its tests."""

from scripts import config


def find_championship(postseason_data):
    """The World Series round from the postseason series data if the team has won it, else None."""
    for series in postseason_data or []:
        if (
            series.get('round') == 'World Series'
            and series.get('status') == 'completed'
            and series.get('result', '').startswith(f"{config.TEAM_ABBR} wins")
        ):
            return series
    return None


def championship_sentence(ws_series):
    """Lead sentence for the summary once the World Series is won."""
    score = ws_series['result'].replace(f"{config.TEAM_ABBR} wins", '').strip()
    opponent = ws_series.get('opponent') or 'their opponent'
    score_text = f" <span class='highlight'>{score}</span>" if score else ''
    return (
        f"The {config.TEAM_NAME_SIMPLE} are <span class='highlight'>World Series champions</span>, "
        f"beating the <span class='highlight'>{opponent}</span>{score_text} for the first title in franchise history."
    )
