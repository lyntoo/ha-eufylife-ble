"""Constants for the EufyLife integration."""

DOMAIN = "eufylife_ble"

# Multi-profile configuration keys
CONF_PROFILES = "profiles"
CONF_PROFILE_NAME = "profile_name"
CONF_WEIGHT_MIN = "weight_min"
CONF_WEIGHT_MAX = "weight_max"

# Per-profile user data keys (also used inside each profile dict)
CONF_USER_AGE = "user_age"
CONF_USER_HEIGHT = "user_height"
CONF_USER_SEX = "user_sex"

# Sex constants
SEX_MALE = "male"
SEX_FEMALE = "female"

# Height unit constants
CONF_HEIGHT_UNIT = "height_unit"
HEIGHT_UNIT_CM = "cm"
HEIGHT_UNIT_FTIN = "ft_in"
DEFAULT_HEIGHT_UNIT = HEIGHT_UNIT_CM
CONF_HEIGHT_FT = "height_ft"
CONF_HEIGHT_IN = "height_in"

# Weight unit constants
CONF_WEIGHT_UNIT = "weight_unit"
WEIGHT_UNIT_KG = "kg"
WEIGHT_UNIT_LBS = "lbs"
DEFAULT_WEIGHT_UNIT = WEIGHT_UNIT_LBS  # User preference: lbs by default
KG_TO_LBS = 2.20462

# Default values
DEFAULT_USER_AGE = 30
DEFAULT_USER_HEIGHT = 170
DEFAULT_USER_SEX = SEX_MALE
# Weight range defaults are in the default unit (lbs)
DEFAULT_WEIGHT_MIN = 66.0   # lbs  (≈ 30 kg)
DEFAULT_WEIGHT_MAX = 330.0  # lbs  (≈ 150 kg)
