class TeaveError(Exception):
    "Base exception for all Teave errors"


class EventDescriptionParsingError(TeaveError):
    "Error parsing configuration from Google Calendar Event description"
