from scraper.kraj import kraj_for


def test_known_points():
    assert kraj_for({"lat": 50.0755, "lon": 14.4378}) == "Praha"
    assert kraj_for({"lat": 50.6104, "lon": 15.6096}) in ("Královéhradecký", "Liberecký")
    assert kraj_for({"lat": 49.7475, "lon": 13.3776}) == "Plzeňský"          # Plzeň
    assert kraj_for({"lat": 49.31, "lon": 14.15}) == "Jihočeský"             # Písek
    assert kraj_for({"lat": 49.1951, "lon": 16.6068}) == "Jihomoravský"      # Brno
    assert kraj_for({"lat": 49.5938, "lon": 17.2509}) == "Olomoucký"         # Olomouc


def test_outside_or_missing():
    assert kraj_for(None) is None
    assert kraj_for({"lat": 48.2, "lon": 16.37}) is None                     # Vídeň
    assert kraj_for({"lat": "x", "lon": 1}) is None
