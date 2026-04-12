from fractions import Fraction
from . import constants


class NoteDuration(object):

  TYPE_RATIO_MAP = {'maxima': Fraction(8, 1), 'long': Fraction(4, 1),
                    'breve': Fraction(2, 1), 'whole': Fraction(1, 1),
                    'half': Fraction(1, 2), 'quarter': Fraction(1, 4),
                    'eighth': Fraction(1, 8), '16th': Fraction(1, 16),
                    '32nd': Fraction(1, 32), '64th': Fraction(1, 64),
                    '128th': Fraction(1, 128), '256th': Fraction(1, 256),
                    '512th': Fraction(1, 512), '1024th': Fraction(1, 1024)}

  def __init__(self, state):
    self.duration = 0  # Duration in normalized ticks (STANDARD_PPQ-based)
    self.midi_ticks = 0  # Duration in MIDI ticks (same as duration after normalization)
    self.seconds = 0  # Duration in seconds
    self.time_position = 0  # Onset time in seconds
    self.xml_position = 0  # Onset in normalized ticks (STANDARD_PPQ-based)
    self.dots = 0  # Number of augmentation dots
    self._type = 'quarter'  # MusicXML duration type
    self.tuplet_ratio = Fraction(1, 1)  # Ratio for tuplets (default to 1)
    self.is_grace_note = True  # Assume true until not found
    self.state = state
    self.preceded_by_grace_note = False  # The note is preceded by a grace note(s)
    self.grace_order = 0  # If there are multiple grace notes, record the order of notes (-1, -2)
    self.num_grace = 0
    self.is_first_grace_note = False

  def parse_duration(self, is_in_chord, is_grace_note, duration):
    """Parse the duration of a note and compute timings.

    All positions and durations are normalized to STANDARD_PPQ ticks per
    quarter note, regardless of the MusicXML <divisions> value. This
    ensures consistent positions even when GP8 exports change divisions
    between measures.
    """
    raw_duration = int(duration)
    # Due to an error in Sibelius' export, force this note to have the
    # duration of the previous note if it is in a chord.
    # previous_note_duration is already normalized.
    if is_in_chord:
      self.midi_ticks = self.state.previous_note_duration
    else:
      # Normalize to lcm_divisions ticks per quarter (always integer)
      self.midi_ticks = raw_duration * (self.state.lcm_divisions // self.state.divisions)

    self.duration = self.midi_ticks

    # seconds still uses STANDARD_PPQ for backwards compatibility
    self.seconds = (raw_duration * (constants.STANDARD_PPQ / self.state.divisions)
                    / constants.STANDARD_PPQ) * self.state.seconds_per_quarter

    self.time_position = float("{0:.8f}".format(self.state.time_position))
    self.xml_position = self.state.xml_position

    # Not sure how to handle durations of grace notes yet as they
    # steal time from subsequent notes and they do not have a
    # <duration> tag in the MusicXML
    self.is_grace_note = is_grace_note

    if is_in_chord:
      # If this is a chord, set the time position to the time position
      # of the previous note (i.e. all the notes in the chord will have
      # the same time position)
      self.time_position = self.state.previous_note_time_position
      self.xml_position = self.state.previous_note_xml_position
    else:
      # Only increment time positions once in chord
      self.state.time_position += self.seconds
      self.state.xml_position += self.midi_ticks

  def _convert_type_to_ratio(self):
    """Convert the MusicXML note-type-value to a Python Fraction.

    Examples:
      "quarter" -> 1/4
      "half" -> 1/2
      "whole" -> 1
      "eighth" -> 1/8

    Returns:
      A Fraction object representing the note type.
    """
    return self.TYPE_RATIO_MAP.get(self._type, Fraction(1, 4))

  @property
  def type(self):
    return self._type

  @type.setter
  def type(self, new_type):
    if new_type is None:
      return
    self._type = new_type

