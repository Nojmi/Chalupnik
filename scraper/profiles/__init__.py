# HOW TO REGISTER A NEW PORTAL PROFILE
# ======================================
# 1. Create scraper/profiles/<portal_slug>.py implementing search(criteria).
#    Use scraper/profiles/_template.py as a starting point.
# 2. Import its search function below and add it to ALL_PROFILES.
#
# Example:
#   from scraper.profiles import chatacentrum
#   ALL_PROFILES = [chatacentrum.search]

ALL_PROFILES: list = []
