from fractions import Fraction

from . import constants
from .chord_symbol import ChordSymbol
from .tempo import Tempo
from .time_signature import TimeSignature
from .key_signature import KeySignature
from .exception import MultipleTimeSignatureException
from .note import Note
from .direction import Direction
from xml.etree import ElementTree as ET
import copy
from pdb import set_trace as st
import random

class Measure(object):
  """Internal represention of the MusicXML <measure> element."""

  def __init__(self, xml_measure, state, predictions = None, guitarPart = None, isFirst = False):
    self.xml_measure = xml_measure
    self.notes = []
    self.directions = []
    self.chord_symbols = []
    self.tempos = []
    self.time_signature = None
    self.key_signature = None
    self.barline = None  # 'double' or 'final' or None
    self.repeat = None  # 'start' or 'jump' or None
    self.segno = None  # 'start' or 'jump' or None
    self.coda = None  # 'start' or 'jump' or None
    self.dacapo = None  # 'jump' or None
    self.fine = False  # True  or False
    self.first_ending_start = False  # 1 or 2 or None
    self.first_ending_stop = False  # 'start' or 'end' or None
    self.isFirstMeasure = isFirst

    # Cumulative duration in MusicXML duration.
    # Used for time signature calculations
    self.duration = 0
    self.implicit = False
    self.state = state
    # Record the starting time of this measure so that time signatures
    # can be inserted at the beginning of the measure
    self.start_time_position = self.state.time_position
    self.start_xml_position = self.state.xml_position

    measureNumber = self.xml_measure.attrib['number']
    width = self.xml_measure.attrib['width']
    self.predictions = predictions
    self.guitarPart = guitarPart
    # print(self.guitarPart)
    if self.guitarPart is not None:
      # print('measa')
      self.guitarMeasureTabElements = []
      self.guitarMeasure = ET.fromstring(
        f'''
        <measure number="{measureNumber}" width="{width}">
      </measure>
      ''')
      self._parse2()

    else:
      self._parse()
    # Update the time signature if a partial or pickup measure
    # self._fix_time_signature()

  def _parse2(self):
    """Parse the <measure> element."""
    # Create new direction
    # direction = []
    if 'implicit' in self.xml_measure.attrib.keys():
      self.implicit = self.xml_measure.attrib['implicit']
    for child in self.xml_measure:

      if child.tag == 'attributes':
        self._parse_attributes(child)
      elif child.tag == 'backup':
        self._parse_backup(child)
        self.guitarMeasure.append(child)
      elif child.tag == 'barline':
        self._parse_barline(child)
        self.guitarMeasure.append(child)
      elif child.tag == 'direction':
        # Get tempo in <sound /> and update state tempo and time_position
        self._parse_direction(child)
        direction = Direction(child, self.state)
        self.directions.append(direction)
        self.guitarMeasure.append(child)
        # self.state.previous_direction = direction
      elif child.tag == 'forward':
        self._parse_forward(child)
        self.guitarMeasure.append(child)
      elif child.tag == 'harmony':
        chord_symbol = ChordSymbol(child, self.state)
        self.chord_symbols.append(chord_symbol)
      elif child.tag == 'note':
        note = Note(child, self.state)
        self.notes.append(note)
        # Keep track of current note as previous note for chord timings
        self.state.previous_note_duration = note.note_duration.duration
        self.state.previous_note_time_position = note.note_duration.time_position
        self.state.previous_note_xml_position = note.note_duration.xml_position

        # Sum up the MusicXML durations in voice 1 of this measure
        if note.voice == 1 and not note.is_in_chord:
          # xribene: this works because is_in_chord is set to true for
          # all the notes in a chord except the first one
          self.duration += note.note_duration.duration

        # create the guitar note
        if note.note_duration.is_grace_note is True:
          pass
        else:

          # childCopy = copy.deepcopy(child)
          childCopy = ET.Element('note')

          # get a single random bernulli trial
          if child.find('rest') is None:
            self.state.note_count += 1
            # use the note_count and the name of the note to create the id of the note
            # also this note_count now matches with the indeces (range) of the predictions

            if random.random() < 0.2:
              # it's decided to ignore this note, so we replace it with a rest
              childCopy.insert(0, ET.Element('rest'))
              for noteElement in child:
                # delete the stem and pitch elements
                if noteElement.tag not in ['stem', 'pitch']:
                  childCopy.append(copy.deepcopy(noteElement))

            else:
              # if the note is "KEEP"
              # TODO: even if the note is "KEEP", the octave might be different.
              # from predictions, take the midi note and convert it to pitch and octave
              childCopy = copy.deepcopy(child)
              child.set('color', 'green')
          else:
            # for rests, our RL agent doesn't make any decisions.
            childCopy = copy.deepcopy(child)

          # st()
          # I use that because the original score might have many staffs (for example piano),
          # but I merge everything in the single staff of the guitar
          childCopy.find('staff').text = '1'


          self.guitarMeasure.append(childCopy)

          tabChildCopy = copy.deepcopy(childCopy)
          tabChildCopy.find('staff').text = '2'
          tabChildCopy.find('voice').text = str(int(childCopy.find('voice').text) + 4)

          if child.find('rest') is None:
            technicalNotation = ET.fromstring(
              f'''<technical>
                <string>5</string>
                <fret>3</fret>
              </technical>
              '''
            )
            # first check if the note has already a notation
            # if it has, append the technicalNotation
            # if not, first create it ET.Element('notation')
            if child.find('notation'):
              pass


          self.guitarMeasureTabElements.append(tabChildCopy)
      else:
        # Ignore other tag types because they are not relevant.
        pass

    # add a backup element to the guitar measure to go back to the start of the measure
    # and add the tabNotes on the staff 2 of the guitar measure
    backup = ET.Element('backup')
    backup.append(ET.Element('duration'))
    backup.find('duration').text = str(self.duration)
    self.guitarMeasure.append(backup)
    # add the tabNotes to the guitar measure
    for tabElement in self.guitarMeasureTabElements:
      self.guitarMeasure.append(tabElement)

    self.guitarPart.append(self.guitarMeasure)

  def _parse(self):
    """Parse the <measure> element."""
    # Create new direction
    # direction = []

    if 'implicit' in self.xml_measure.attrib.keys():
      self.implicit = self.xml_measure.attrib['implicit']
    for child in self.xml_measure:

      if child.tag == 'attributes':
        self._parse_attributes(child)
      elif child.tag == 'backup':
        self._parse_backup(child)
      elif child.tag == 'barline':
        self._parse_barline(child)
      elif child.tag == 'direction':
        # Get tempo in <sound /> and update state tempo and time_position
        self._parse_direction(child)
        direction = Direction(child, self.state)
        self.directions.append(direction)
        # self.state.previous_direction = direction
      elif child.tag == 'forward':
        self._parse_forward(child)
      elif child.tag == 'harmony':
        chord_symbol = ChordSymbol(child, self.state)
        self.chord_symbols.append(chord_symbol)
      elif child.tag == 'note':
        note = Note(child, self.state)
        self.notes.append(note)
        # Keep track of current note as previous note for chord timings
        self.state.previous_note_duration = note.note_duration.duration
        self.state.previous_note_time_position = note.note_duration.time_position
        self.state.previous_note_xml_position = note.note_duration.xml_position

        # Sum up the MusicXML durations in voice 1 of this measure
        if note.voice == 1 and not note.is_in_chord:
          self.duration += note.note_duration.duration
      else:
        # Ignore other tag types because they are not relevant.
        pass

  def _parse_barline(self, xml_barline):
    """Parse the MusicXML <barline> element.

    Args:
      xml_barline: XML element with tag type 'barline'.
    """
    style = xml_barline.find('bar-style')
    if style is not None:
      style = xml_barline.find('bar-style').text
    repeat = xml_barline.find('repeat')
    ending = xml_barline.find('ending')

    if style == 'light-light':
      self.barline = 'double'
    elif style == 'light-heavy':
      self.barline = 'final'

    if repeat is not None:
      attrib = repeat.attrib['direction']
      if attrib == 'forward':
        self.repeat = 'start'
      elif attrib == 'backward':
        self.repeat = 'jump'

    if ending is not None:
      ending_num = ending.attrib['number']
      ending_type = ending.attrib['type']
      if ending_num == '1' and ending_type == 'start':
        self.first_ending_start = True
      elif ending_num == '1' and ending_type == 'stop':
        self.first_ending_stop = True
      elif ending_num == '1' and ending_type == 'discontinue':
        self.state.first_ending_discontinue = True

  def _parse_attributes(self, xml_attributes):
    """Parse the MusicXML <attributes> element."""

    # create a attributes element for the guitar part
    guitarAttributes = ET.Element('attributes')

    for child in xml_attributes:
      if child.tag == 'divisions':
        self.state.divisions = int(child.text)
        # add the divisions to the guitar attributes
        guitarAttributes.append(copy.deepcopy(child))
      elif child.tag == 'key':
        self.key_signature = KeySignature(self.state, child)
        guitarAttributes.append(copy.deepcopy(child))
      elif child.tag == 'time':
        if self.time_signature is None:
          self.time_signature = TimeSignature(self.state, child)
          self.state.time_signature = self.time_signature
          # add the time signature to the guitar attributes
          guitarAttributes.append(copy.deepcopy(child))
        else:
          raise MultipleTimeSignatureException('Multiple time signatures')
      elif child.tag == 'transpose':
        transpose = int(child.find('chromatic').text)
        self.state.transpose = transpose
        if self.key_signature is not None:
          # Transposition is chromatic. Every half step up is 5 steps backward
          # on the circle of fifths, which has 12 positions.
          key_transpose = (transpose * -5) % 12
          new_key = self.key_signature.key + key_transpose
          # If the new key has >6 sharps, translate to flats.
          # TODO(fjord): Could be more smart about when to use sharps vs. flats
          # when there are enharmonic equivalents.
          if new_key > 6:
            new_key %= -6
          self.key_signature.key = new_key

      else:
        # Ignore other tag types because they are not relevant to mxp.
        pass

    # add the following attributes to the guitar part
    if self.isFirstMeasure is True:
      staves = ET.fromstring(f'''<staves>2</staves>''')
      clef1 = ET.fromstring(
        f'''<clef number="1">
        <sign>G</sign>
        <line>2</line>
        <clef-octave-change>-1</clef-octave-change>
        </clef>''')
      clef2 = ET.fromstring(
        f'''<clef number="2">
        <sign>TAB</sign>
        <line>5</line>
        </clef>'''
      )
      staffDetails =  ET.fromstring(
        f'''
      <staff-details number="2">
        <staff-lines>6</staff-lines>
        <staff-tuning line="1">
          <tuning-step>E</tuning-step>
          <tuning-octave>2</tuning-octave>
          </staff-tuning>
        <staff-tuning line="2">
          <tuning-step>A</tuning-step>
          <tuning-octave>2</tuning-octave>
          </staff-tuning>
        <staff-tuning line="3">
          <tuning-step>D</tuning-step>
          <tuning-octave>3</tuning-octave>
          </staff-tuning>
        <staff-tuning line="4">
          <tuning-step>G</tuning-step>
          <tuning-octave>3</tuning-octave>
          </staff-tuning>
        <staff-tuning line="5">
          <tuning-step>B</tuning-step>
          <tuning-octave>3</tuning-octave>
          </staff-tuning>
        <staff-tuning line="6">
          <tuning-step>E</tuning-step>
          <tuning-octave>4</tuning-octave>
          </staff-tuning>
        </staff-details>
      ''')
      guitarAttributes.append(staves)
      guitarAttributes.append(clef1)
      guitarAttributes.append(clef2)
      guitarAttributes.append(staffDetails)

    self.guitarMeasure.append(guitarAttributes)



  def _parse_backup(self, xml_backup):
    """Parse the MusicXML <backup> element.

    This moves the global time position backwards.

    Args:
      xml_backup: XML element with tag type 'backup'.
    """

    xml_duration = xml_backup.find('duration')
    backup_duration = int(xml_duration.text)
    midi_ticks = backup_duration * (constants.STANDARD_PPQ
                                    / self.state.divisions)
    seconds = ((midi_ticks / constants.STANDARD_PPQ)
               * self.state.seconds_per_quarter)
    self.state.time_position -= seconds
    self.state.xml_position -= backup_duration

    self.guitarMeasure.append(copy.deepcopy(xml_backup))
    self.guitarMeasureTabElements.append(copy.deepcopy(xml_backup))

  def _parse_direction(self, xml_direction):
    """Parse the MusicXML <direction> element."""
    for child in xml_direction:
      if child.tag == 'sound':
        if child.get('tempo') is not None:
          tempo = Tempo(self.state, child)
          self.tempos.append(tempo)
          self.state.qpm = tempo.qpm
          self.state.seconds_per_quarter = 60 / self.state.qpm
          if child.get('dynamics') is not None:
            self.state.velocity = int(child.get('dynamics'))
        elif child.get('dacapo') is not None:
          self.dacapo = 'jump'
        elif child.get('fine') is not None:
          self.fine = True
        elif child.get('alcoda') is not None:
          self.coda = 'jump'
        elif child.get('tocoda') is not None:
          self.coda = 'jump'
        elif child.get('coda') is not None:
          self.coda = 'start'
        elif child.get('dalsegno') is not None:
          self.segno = 'jump'
        elif child.get('segno') is not None:
          self.segno = 'start'
      if self.state.first_ending_discontinue and child.tag=='direction-type':
        child_list = list(child)
        for sub_child in child_list:
          if sub_child.tag=='bracket' and sub_child.get('type')=='stop':
            self.first_ending_stop = True
            self.state.first_ending_discontinue = False


  def _parse_forward(self, xml_forward):
    """Parse the MusicXML <forward> element.

    This moves the global time position forward.

    Args:
      xml_forward: XML element with tag type 'forward'.
    """

    xml_duration = xml_forward.find('duration')
    forward_duration = int(xml_duration.text)
    midi_ticks = forward_duration * (constants.STANDARD_PPQ
                                     / self.state.divisions)
    seconds = ((midi_ticks / constants.STANDARD_PPQ)
               * self.state.seconds_per_quarter)
    self.state.time_position += seconds
    self.state.xml_position += forward_duration

    self.guitarMeasure.append(copy.deepcopy(xml_forward))
    self.guitarMeasureTabElements.append(copy.deepcopy(xml_forward))

  def _fix_time_signature(self):
    """Correct the time signature for incomplete measures.

    If the measure is incomplete or a pickup, insert an appropriate
    time signature into this Measure.
    """
    # Compute the fractional time signature (duration / divisions)
    # Multiply divisions by 4 because division is always parts per quarter note
    numerator = self.duration
    denominator = self.state.divisions * 4
    fractional_time_signature = Fraction(numerator, denominator)

    if self.state.time_signature is None and self.time_signature is None:
      # No global time signature yet and no measure time signature defined
      # in this measure (no time signature or senza misura).
      # Insert the fractional time signature as the time signature
      # for this measure
      self.time_signature = TimeSignature(self.state)
      self.time_signature.numerator = fractional_time_signature.numerator
      self.time_signature.denominator = fractional_time_signature.denominator
      self.state.time_signature = self.time_signature
    else:
      fractional_state_time_signature = Fraction(
        self.state.time_signature.numerator,
        self.state.time_signature.denominator)

      # Check for pickup measure. Reset time signature to smaller numerator
      pickup_measure = False
      if numerator < self.state.time_signature.numerator:
        pickup_measure = True

      # Get the current time signature denominator
      global_time_signature_denominator = self.state.time_signature.denominator

      # If the fractional time signature = 1 (e.g. 4/4),
      # make the numerator the same as the global denominator
      if fractional_time_signature == 1 and not pickup_measure:
        new_time_signature = TimeSignature(self.state)
        new_time_signature.numerator = global_time_signature_denominator
        new_time_signature.denominator = global_time_signature_denominator
      else:
        # Otherwise, set the time signature to the fractional time signature
        # Issue #674 - Use the original numerator and denominator
        # instead of the fractional one
        new_time_signature = TimeSignature(self.state)
        new_time_signature.numerator = numerator
        new_time_signature.denominator = denominator

        new_time_sig_fraction = Fraction(numerator,
                                         denominator)

        if new_time_sig_fraction == fractional_time_signature:
          new_time_signature.numerator = fractional_time_signature.numerator
          new_time_signature.denominator = fractional_time_signature.denominator

      # Insert a new time signature only if it does not equal the global
      # time signature.
      if (pickup_measure or
          (self.time_signature is None
           and (fractional_time_signature != fractional_state_time_signature))):
        new_time_signature.time_position = self.start_time_position
        new_time_signature.xml_position = self.start_xml_position
        self.time_signature = new_time_signature
        self.state.time_signature = new_time_signature
