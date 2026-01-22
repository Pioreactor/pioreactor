# -*- coding: utf-8 -*-
# types
import typing as t

from msgspec import Meta
from pioreactor.states import JobState  # noqa: F401

if t.TYPE_CHECKING:
    from pioreactor.pubsub import Client
    from pioreactor.logging import CustomLogger


type Unit = str
type Experiment = str


class DosingProgram(t.Protocol):
    """
    Should return a non-negative float representing (approx) how much liquid was moved, in ml.
    """

    def __call__(
        self,
        unit: str,
        experiment: str,
        ml: float,
        source_of_event: str,
        mqtt_client: t.Optional["Client"] = None,
        logger: t.Optional["CustomLogger"] = None,
    ) -> float:
        # don't forget to return a float!
        ...


type MQTTMessagePayload = bytes | bytearray


class MQTTMessage:
    payload: MQTTMessagePayload
    topic: str
    qos: t.Literal[0, 1, 2]
    retain: bool
    mid: int


type PublishableSettingDataType = str | float | int | bool


class PublishableSetting(t.TypedDict, total=False):
    """
    In a job, the published_settings attribute is a list of dictionaries that have
    the below schema.

    datatype:
        string: a string
        float: a float
        integer: an integer
        json: this can have arbitrary data in it.
        boolean: must be 0 or 1 (this is unlike the Homie convention)
        Automation: json encoded struct.Automation

    unit (optional):
        a string representing what the unit suffix is

    settable:
        a bool representing if the attribute can be changed over MQTT

    persist (optional):
        a bool representing if the attr should be cleared when the job cleans up. Default False.

    """

    datatype: t.Required[
        t.Literal[
            "string",
            "float",
            "integer",
            "json",
            "boolean",
            "GrowthRate",
            "ODFiltered",
            "ODFused",
            "Temperature",
            "MeasuredRPM",
            "AutomationEvent",
            "Voltage",
            "KalmanFilterOutput",
            "ODReadings",
            "ODReading",
            "RawODReading",
            "CalibratedODReading",
        ]
    ]
    unit: t.NotRequired[str]
    settable: t.Required[bool]
    persist: t.NotRequired[bool]


type LedChannel = t.Literal["A", "B", "C", "D"]
# these are strings! Don't make them ints, since ints suggest we can perform math on them, that's meaningless.
# str suggest symbols, which they are.
type PdChannel = t.Literal["1", "2", "3", "4"]
type PwmChannel = t.Literal["1", "2", "3", "4", "5"]

type PdAngle = t.Literal["45", "90", "135", "180"]
type PdAngleOrREF = PdAngle | t.Literal["REF"]

# hardware level stuff
type AnalogValue = int | float
type Voltage = float  # maybe should be non-negative?
type RawOD = t.Annotated[float, Meta(ge=0)]
type CalibratedOD = float
type OD = RawOD | CalibratedOD

type AdcChannel = int  # non-negative

type FloatBetween0and100 = t.Annotated[float, Meta(ge=0, le=100)]
type LedIntensityValue = FloatBetween0and100

# All GPIO pins below are BCM numbered
type GpioPin = t.Literal[
    2,
    3,
    4,
    14,
    15,
    17,
    18,
    27,
    22,
    23,
    24,
    10,
    9,
    25,
    11,
    8,
    7,
    0,
    1,
    5,
    6,
    12,
    13,
    19,
    16,
    26,
    20,
    21,
]

type I2CPin = GpioPin | tuple[int, GpioPin]
type I2CAddress = int  # 0 <= I2CAddress <= 127

type GpioChip = t.Literal[0, 4]

type mL = float
type Seconds = float

# calibration data
OD_DEVICES = ["od", "od45", "od90", "od135"]
OD_FUSED_DEVICE = "od_fused"
PUMP_DEVICES = ["media_pump", "alt_media_pump", "waste_pump"]

type ODCalibrationDevices = t.Literal["od", "od45", "od90", "od135"]
type ODFusedCalibrationDevice = t.Literal["od_fused"]
type PumpCalibrationDevices = t.Literal["media_pump", "alt_media_pump", "waste_pump"]

type PolyFitCoefficients = list[float]
type SplineFitKnots = list[float]
type SplineFitCoefficients = list[list[float]]
type SplineFitData = list[SplineFitKnots | SplineFitCoefficients]
type CalibrationCurveData = PolyFitCoefficients | SplineFitData
