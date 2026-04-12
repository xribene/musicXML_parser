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
from pdb import set_trace
import random


class Measure(object):
    """Internal represention of the MusicXML <measure> element."""

    def __init__(
        self,
        xml_measure,
        xml_parent_part,
        state,
        predictions=None,
        guitarPartsET=None,
        isFirst=False,
        noteCounter=0,
    ):
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
        self.noteCounter = noteCounter
        self.parent_part = xml_parent_part

        # Cumulative duration in MusicXML duration.
        # Used for time signature calculations
        self.duration = 0
        self.implicit = False
        self.state = state
        # Record the starting time of this measure so that time signatures
        # can be inserted at the beginning of the measure
        self.start_time_position = self.state.time_position
        self.start_xml_position = self.state.xml_position
        self._max_xml_position = self.state.xml_position

        measureNumber = self.xml_measure.attrib["number"]
        # check if the measure has a width attribute
        if "width" in self.xml_measure.attrib.keys():
            width = self.xml_measure.attrib["width"]
        else:
            width = "0"
        self.predictions = predictions
        self.guitarPartsET = guitarPartsET
        # print(self.guitarPart)
        self.guitarMeasuresET = []
        self.guitarMeasuresTabElements = []
        if self.guitarPartsET is not None:
            for i, tab_part in enumerate(self.predictions["parts"]):
                self.guitarMeasuresTabElements.append([])
                self.guitarMeasuresET.append(
                    ET.fromstring(
                        f"""
                    <measure number="{measureNumber}">
                    </measure>
                    """
                    )
                )
            self._parse2()
        else:
            self._parse()

        # Fix xml_position: GP8 exports may not fill incomplete voices
        # with rests, leaving the position counter mid-measure.
        # Two cases:
        # 1) Incomplete last voice: max_pos > current_pos → use max_pos
        # 2) Empty measure (repeat/segno/coda): max_pos == start → advance
        #    by expected measure length from time signature
        if hasattr(self, '_max_xml_position'):
            if self._max_xml_position > self.start_xml_position:
                # Measure has content — use the longest voice's end
                if self.state.xml_position < self._max_xml_position:
                    self.state.xml_position = self._max_xml_position
            else:
                # Empty measure — advance by expected length
                expected_length = (
                    self.state.time_signature.numerator
                    * self.state.lcm_divisions * 4
                    // self.state.time_signature.denominator
                )
                self.state.xml_position = self.start_xml_position + expected_length

        # Update the time signature if a partial or pickup measure
        # self._fix_time_signature()

    def _parse2(self):
        """Parse the <measure> element."""
        # Create new direction
        # direction = []
        if "implicit" in self.xml_measure.attrib.keys():
            self.implicit = self.xml_measure.attrib["implicit"]
        for child in self.xml_measure:
            if child.tag == "attributes":
                self._parse_attributes(child)
            elif child.tag == "backup":
                # TODO: There is a bug here that thankfully doesn't affect the XML output
                # there is no way for me to ignore backups that are in the original TAB staff
                # For notes it's easy because I can just check their staff number and skip them
                # but for backups, I can't do that because they don't have a staff number
                self._parse_backup(child)
                [
                    guitarMeasure.append(copy.deepcopy(child))
                    for guitarMeasure in self.guitarMeasuresET
                ]
                [
                    guitarMeasureTabElements.append(copy.deepcopy(child))
                    for guitarMeasureTabElements in self.guitarMeasuresTabElements
                ]
            elif child.tag == "barline":
                self._parse_barline(child)
                [
                    guitarMeasure.append(copy.deepcopy(child))
                    for guitarMeasure in self.guitarMeasuresET
                ]
            elif child.tag == "direction":
                # Get tempo in <sound /> and update state tempo and time_position
                self._parse_direction(child)
                direction = Direction(child, self.state)
                self.directions.append(direction)
                # [
                #     guitarMeasure.append(copy.deepcopy(child))
                #     for guitarMeasure in self.guitarMeasuresET
                # ]
                # self.state.previous_direction = direction
            elif child.tag == "forward":
                self._parse_forward(child)
                [
                    guitarMeasure.append(copy.deepcopy(child))
                    for guitarMeasure in self.guitarMeasuresET
                ]
                [
                    guitarMeasureTabElements.append(copy.deepcopy(child))
                    for guitarMeasureTabElements in self.guitarMeasuresTabElements
                ]
            elif child.tag == "harmony":
                chord_symbol = ChordSymbol(child, self.state)
                self.chord_symbols.append(chord_symbol)
            elif child.tag == "note":
                note = Note(child, self, self.state)
                self.notes.append(note)
                # Keep track of current note as previous note for chord timings
                self.state.previous_note_duration = note.note_duration.duration
                self.state.previous_note_time_position = (
                    note.note_duration.time_position
                )
                self.state.previous_note_xml_position = note.note_duration.xml_position
                if self.state.xml_position > self._max_xml_position:
                    self._max_xml_position = self.state.xml_position

                # Sum up the MusicXML durations in voice 1 of this measure
                if note.voice == 1 and not note.is_in_chord:
                    # xribene: this works because is_in_chord is set to true for
                    # all the notes in a chord except the first one
                    self.duration += note.note_duration.duration

                if note.note_duration.is_grace_note is True:
                    continue

                if child.find("rest") is None:
                    self.state.note_count += 1
                    self.noteCounter += 1
                    assert self.state.note_count == self.noteCounter

                if note.is_tab_note or note.notehead_type == "diamond":
                    # This is a tab note, and in the task of tablature-assignment (ReductedMusicXML) we ignore it
                    # because it messes up our note-indices.
                    # I also make sure this check happens after the noteCounter is incremented
                    # because the tab-notes were considered when parsing the original score during dataset creation
                    continue

                childCopy = copy.deepcopy(child)
                if child.find("rest") is None:
                    childCopy.find("pitch").find("octave").text = str(
                        int(childCopy.find("pitch").find("octave").text) - 1
                    )

                # Some cleaning on the childCopy before we create the tabChildCopy
                prev_notations = childCopy.find("notations")
                if prev_notations is not None:
                    # childCopy.remove(prev_notations)

                    # If there is already a notation element,
                    # Check if it includes <fingering>
                    # if yes, we need to delete it.
                    # Get the notations element

                    # Get the technical element
                    prev_technical = prev_notations.find("technical")
                    if prev_technical is not None:
                        # if there is <fingering> element, remove it
                        # prev_fingering = prev_technical.find('fingering')
                        # if prev_fingering is not None:
                        #   prev_technical.remove(prev_fingering)
                        # prev_open_string = prev_technical.find('open-string')
                        # if prev_open_string is not None:
                        #   prev_technical.remove(prev_open_string)

                        # Delete the prev_technical element
                        prev_notations.remove(prev_technical)

                listTabChildren = []
                for i, tab_part in enumerate(self.predictions["parts"]):

                    tabChild = copy.deepcopy(childCopy)
                    tabChild.find("staff").text = (
                        f"{2 - int(self.predictions['single_staff_tab'])}"
                    )
                    tabChild.find("voice").text = str(
                        int(childCopy.find("voice").text) + (i + 1) * 5
                    )
                    if child.find("rest") is None:
                        tab = tab_part["tab"]
                        assert self.state.note_count == self.noteCounter

                        note_tab_pred = None
                        if self.noteCounter in tab.keys():
                            note_tab_pred = tab[self.noteCounter]
                        else:
                            if note.note_notations.tied_stop is True:
                                pass
                            else:
                                # Instead of raising exception, print a waning
                                print(
                                    f"No prediction for note {self.noteCounter-1} in part {i}"
                                )
                                # And paint the child in red
                                # Set the color of the tied note to blue
                                notehead = child.find("notehead")
                                if notehead is None:
                                    notehead = ET.Element("notehead")
                                    notehead.text = "normal"
                                    notehead.set("color", "#FF0000")
                                    child.append(notehead)
                                else:
                                    notehead.set("color", "#FF0000")
                                # Make tabChild a rest with the same durationt
                                tabChild.remove(tabChild.find("pitch"))
                                tabChild.append(ET.Element("rest"))
                                tabChild.find("rest").append(ET.Element("display-step"))
                                listTabChildren.append(tabChild)
                                continue
                                # tabChild.find("rest").find("display-step").text = "C"
                                # tabChild.find("rest").append(ET.Element("display-octave"))
                                # tabChild.find("rest").find("display-octave").text = "4"
                                # tabChild.find("duration").text = str(
                                #     int(tabChild.find("duration").text)
                                # )

                        # use the note_count and the name of the note to create the id of the note
                        # also this note_count now matches with the indeces (range) of the predictions
                        if note_tab_pred is not None:

                            # childCopy = copy.deepcopy(child)
                            # child.set("color", "#00FF00")
                            # 0 - Mi 6th, 1 - La 5th, 2 - Re 4th, 3 - Sol 3rd, 4 - Si 2nd, 5 - Mi 1st
                            string = note_tab_pred[0]
                            fret = note_tab_pred[1]

                            # make sure the chromatic pitch class of the prediction is the same
                            # as the note in the original score. If it is, then I can safely use the
                            # pitch element of the oriinal score.
                            tuning_based_midi = (
                                self.predictions["tuning_midi"][string] + fret
                            )
                            assert note.pitch[1] % 12 == tuning_based_midi % 12
                            technicalNotation = ET.Element("technical")
                            stringElement = ET.SubElement(technicalNotation, "string")
                            stringElement.text = str(6 - string)
                            fretElement = ET.SubElement(technicalNotation, "fret")
                            fretElement.text = str(fret)

                            # first check if the note has already a notation
                            # if it has, append the technicalNotation
                            # if not, first create it ET.Element('notation')
                            prev_notations = tabChild.find("notations")
                            if prev_notations is not None:
                                # Append the new technicalNotation
                                prev_notations.append(technicalNotation)

                            else:
                                tabChild.append(ET.Element("notations"))
                                tabChild.find("notations").append(technicalNotation)
                                
                        else:
                            if note.note_notations.tied_stop is False:
                                raise Exception(
                                    f"No prediction for note {self.noteCounter-1}"
                                )
                            else:
                                # Set the color of the tied note to blue
                                notehead = tabChild.find("notehead")
                                if notehead is None:
                                    notehead = ET.Element("notehead")
                                    notehead.text = "normal"
                                    notehead.set("color", "#00FF00")
                                    tabChild.append(notehead)
                                else:
                                    notehead.set("color", "#00FF00")

                    listTabChildren.append(tabChild)

                if self.predictions["single_staff_tab"] is False:
                    [
                        guitarMeasure.append(copy.deepcopy(childCopy))
                        for guitarMeasure in self.guitarMeasuresET
                    ]
                [
                    guitarMeasureTabElements.append(tabChild)
                    for guitarMeasureTabElements, tabChild in zip(
                        self.guitarMeasuresTabElements, listTabChildren
                    )
                ]
        if self.predictions["single_staff_tab"] is False:
            # add a backup element to the guitar measure to go back to the start of the measure
            # and add the tabNotes on the staff 2 of the guitar measure
            backup = ET.Element("backup")
            backup.append(ET.Element("duration"))
            backup.find("duration").text = str(self.duration)
            # self.guitarMeasure.append(backup)
            [
                guitarMeasure.append(copy.deepcopy(backup))
                for guitarMeasure in self.guitarMeasuresET
            ]
        # # add the tabNotes to each guitar measure
        # for tabElement in self.guitarMeasureTabElements:
        #     self.guitarMeasure.append(tabElement)
        [
            guitarMeasure.extend(tabElement)
            for guitarMeasure, tabElement in zip(
                self.guitarMeasuresET, self.guitarMeasuresTabElements
            )
        ]
        # self.guitarPart.append(self.guitarMeasure)
        [
            guitarPartET.append(guitarMeasure)
            for guitarMeasure, guitarPartET in zip(
                self.guitarMeasuresET, self.guitarPartsET
            )
        ]

    def _parse(self):
        """Parse the <measure> element."""
        # Create new direction
        # direction = []

        if "implicit" in self.xml_measure.attrib.keys():
            self.implicit = self.xml_measure.attrib["implicit"]
        for child in self.xml_measure:

            if child.tag == "attributes":
                self._parse_attributes(child)
            elif child.tag == "backup":
                self._parse_backup(child)
            elif child.tag == "barline":
                self._parse_barline(child)
            elif child.tag == "direction":
                # Get tempo in <sound /> and update state tempo and time_position
                self._parse_direction(child)
                direction = Direction(child, self.state)
                self.directions.append(direction)
                # self.state.previous_direction = direction
            elif child.tag == "forward":
                self._parse_forward(child)
            elif child.tag == "harmony":
                chord_symbol = ChordSymbol(child, self.state)
                self.chord_symbols.append(chord_symbol)
            elif child.tag == "note":
                note = Note(child, self, self.state)
                self.notes.append(note)
                # Keep track of current note as previous note for chord timings
                self.state.previous_note_duration = note.note_duration.duration
                self.state.previous_note_time_position = (
                    note.note_duration.time_position
                )
                self.state.previous_note_xml_position = note.note_duration.xml_position
                if self.state.xml_position > self._max_xml_position:
                    self._max_xml_position = self.state.xml_position

                # Sum up the MusicXML durations in voice 1 of this measure
                if note.voice == 1 and not note.is_in_chord:
                    # xribene: this works because is_in_chord is set to true for
                    # all the notes in a chord except the first one
                    self.duration += note.note_duration.duration

                # add an ID only to the notes that we are interested for score-reduction
                # this id-ing process and note selection needs to be identical to the one in _parse2
                # so during the creation of the guitar-score we can match the notes using the id
                if note.note_duration.is_grace_note is True:
                    pass
                else:
                    if child.find("rest") is None:
                        self.state.note_count += 1
                        note.id = self.state.note_count

            else:
                # Ignore other tag types because they are not relevant.
                pass

    def _parse_barline(self, xml_barline):
        """Parse the MusicXML <barline> element.

        Args:
          xml_barline: XML element with tag type 'barline'.
        """
        style = xml_barline.find("bar-style")
        if style is not None:
            style = xml_barline.find("bar-style").text
        repeat = xml_barline.find("repeat")
        ending = xml_barline.find("ending")

        if style == "light-light":
            self.barline = "double"
        elif style == "light-heavy":
            self.barline = "final"

        if repeat is not None:
            attrib = repeat.attrib["direction"]
            if attrib == "forward":
                self.repeat = "start"
            elif attrib == "backward":
                self.repeat = "jump"

        if ending is not None:
            ending_num = ending.attrib["number"]
            ending_type = ending.attrib["type"]
            if ending_num == "1" and ending_type == "start":
                self.first_ending_start = True
            elif ending_num == "1" and ending_type == "stop":
                self.first_ending_stop = True
            elif ending_num == "1" and ending_type == "discontinue":
                self.state.first_ending_discontinue = True

    def _parse_attributes(self, xml_attributes):
        """Parse the MusicXML <attributes> element."""

        # create a attributes element for the guitar part
        guitarAttributes = ET.Element("attributes")

        for child in xml_attributes:
            if child.tag == "divisions":
                self.state.divisions = int(child.text)
                # add the divisions to the guitar attributes
                guitarAttributes.append(copy.deepcopy(child))
            elif child.tag == "key":
                self.key_signature = KeySignature(self.state, child)
                guitarAttributes.append(copy.deepcopy(child))
            elif child.tag == "time":
                if self.time_signature is None:
                    self.time_signature = TimeSignature(self.state, child)
                    self.state.time_signature = self.time_signature
                    # add the time signature to the guitar attributes
                    guitarAttributes.append(copy.deepcopy(child))
                else:
                    raise MultipleTimeSignatureException("Multiple time signatures")
            elif child.tag == "staves":
                # TODO: handle guitarAttributes
                self.parent_part.num_staves = int(child.text)
            elif child.tag == "clef":
                clef_sign = child.find("sign")
                if clef_sign is not None:
                    clef_sign = clef_sign.text
                clef_line = child.find("line")
                if clef_line is not None:
                    clef_line = int(clef_line.text)
                clef_octave_change = child.find("clef-octave-change")
                if clef_octave_change is not None:
                    clef_octave_change = int(clef_octave_change.text)

                self.parent_part.clefs.append(
                    {
                        "sign": clef_sign,
                        "line": clef_line,
                        "clef-octave-change": clef_octave_change,
                    }
                )
            elif child.tag == "staff-details":
                staff_id = int(child.attrib["number"])
                # I'm assuming the clefs have been parsed before the staff-details
                current_clef = self.parent_part.clefs[staff_id - 1]
                if current_clef["sign"] == "TAB":
                    self.parent_part.tab_staff_ind = staff_id
                    self.parent_part.has_tab = True
                    staff_lines_el = child.find("staff-lines")
                    if staff_lines_el is None:
                        # GP8 can emit <staff-details> without <staff-lines>
                        continue
                    self.parent_part.num_strings = int(staff_lines_el.text)
                    xml_staff_tuning = child.findall("staff-tuning")
                    # If <staff-type>alternate</staff-type> exists in
                    if child.find("staff-type") is not None:
                        if child.find("staff-type").text == "alternate":
                            self.parent_part.is_alternate_tuning = True
                    assert len(xml_staff_tuning) == self.parent_part.num_strings
                    self.parent_part.tuning = [None] * self.parent_part.num_strings
                    for tuning in xml_staff_tuning:
                        line_idx = int(tuning.attrib["line"]) - 1
                        step = tuning.find("tuning-step").text
                        octave = int(tuning.find("tuning-octave").text)
                        alter = ""
                        if tuning.find("tuning-alter") is not None:
                            alter = int(tuning.find("tuning-alter").text)
                            if alter == 1:
                                alter = "#"
                            elif alter == -1:
                                alter = "b"
                        self.parent_part.tuning[line_idx] = (step, octave, alter)
            elif child.tag == "transpose":
                transpose = int(child.find("chromatic").text)
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
        if self.guitarPartsET is not None:
            if self.isFirstMeasure is True:
                num_staves = 2 - int(self.predictions["single_staff_tab"])
                staves = ET.fromstring(f"""<staves>{num_staves}</staves>""")
                # If num_staves == 2 then we add a G clef and a TAB clef
                # if num_staves == 1 then we only use a TAB clef
                tab_clef = ET.Element("clef")
                tab_clef_sign = ET.SubElement(tab_clef, "sign")
                tab_clef_sign.text = "TAB"
                tab_clef_line = ET.SubElement(tab_clef, "line")
                tab_clef_line.text = "5"
                if num_staves == 2:
                    clef1 = ET.Element("clef")
                    clef1.set("number", "1")
                    clef1_sign = ET.SubElement(clef1, "sign")
                    clef1_sign.text = "G"
                    clef1_line = ET.SubElement(clef1, "line")
                    clef1_line.text = "2"
                    clef1_octave_change = ET.SubElement(clef1, "clef-octave-change")
                    clef1_octave_change.text = "-1"

                    clef2 = tab_clef
                    tab_clef.set("number", "2")
                else:
                    clef1 = tab_clef
                    clef1.set("number", "1")

                # Get the tuning in MIDI from the predictions
                tuning_xml = self.predictions["tuning_xml"]
                # Replace the hardcoded staffDetails with a dynamically generated one
                staffDetails = ET.Element("staff-details")
                # if num_staves == 2 then the TAB is the second staff
                # if num_staves == 1 then the TAB is the first staff
                staffDetails.set("number", f"{num_staves}")

                staff_lines = ET.SubElement(staffDetails, "staff-lines")
                staff_lines.text = "6"

                # Loop through the tuning_xml to create staff-tuning elements
                for i, (step, octave, alter) in enumerate(tuning_xml, 1):
                    # Create staff-tuning element for each string
                    staff_tuning = ET.SubElement(staffDetails, "staff-tuning")
                    staff_tuning.set("line", str(i))

                    # Add tuning-step
                    tuning_step = ET.SubElement(staff_tuning, "tuning-step")
                    tuning_step.text = step

                    # Add tuning-octave
                    tuning_octave = ET.SubElement(staff_tuning, "tuning-octave")
                    tuning_octave.text = str(octave)

                    # Only add tuning-alter if it's not 0.0
                    if alter != 0.0:
                        tuning_alter = ET.SubElement(staff_tuning, "tuning-alter")
                        tuning_alter.text = str(
                            int(alter) if alter.is_integer() else alter
                        )

                guitarAttributes.append(staves)
                guitarAttributes.append(clef1)
                if num_staves == 2:
                    guitarAttributes.append(clef2)
                guitarAttributes.append(staffDetails)

            [
                guitarMeasure.append(copy.deepcopy(guitarAttributes))
                for guitarMeasure in self.guitarMeasuresET
            ]

    def _parse_backup(self, xml_backup):
        """Parse the MusicXML <backup> element.

        This moves the global time position backwards.

        Args:
          xml_backup: XML element with tag type 'backup'.
        """

        xml_duration = xml_backup.find("duration")
        backup_duration = int(xml_duration.text)
        midi_ticks = backup_duration * (constants.STANDARD_PPQ / self.state.divisions)
        normalized = backup_duration * (self.state.lcm_divisions // self.state.divisions)
        seconds = (midi_ticks / constants.STANDARD_PPQ) * self.state.seconds_per_quarter
        self.state.time_position -= seconds
        self.state.xml_position -= normalized

        # self.guitarMeasure.append(copy.deepcopy(xml_backup))
        # self.guitarMeasureTabElements.append(copy.deepcopy(xml_backup))

    def _parse_direction(self, xml_direction):
        """Parse the MusicXML <direction> element."""
        for child in xml_direction:
            if child.tag == "sound":
                if child.get("tempo") is not None:
                    tempo = Tempo(self.state, child)
                    self.tempos.append(tempo)
                    self.state.qpm = tempo.qpm
                    self.state.seconds_per_quarter = 60 / self.state.qpm
                    if child.get("dynamics") is not None:
                        self.state.velocity = int(child.get("dynamics"))
                elif child.get("dacapo") is not None:
                    self.dacapo = "jump"
                elif child.get("fine") is not None:
                    self.fine = True
                elif child.get("alcoda") is not None:
                    self.coda = "jump"
                elif child.get("tocoda") is not None:
                    self.coda = "jump"
                elif child.get("coda") is not None:
                    self.coda = "start"
                elif child.get("dalsegno") is not None:
                    self.segno = "jump"
                elif child.get("segno") is not None:
                    self.segno = "start"
            if self.state.first_ending_discontinue and child.tag == "direction-type":
                child_list = list(child)
                for sub_child in child_list:
                    if sub_child.tag == "bracket" and sub_child.get("type") == "stop":
                        self.first_ending_stop = True
                        self.state.first_ending_discontinue = False

    def _parse_forward(self, xml_forward):
        """Parse the MusicXML <forward> element.

        This moves the global time position forward.

        Args:
          xml_forward: XML element with tag type 'forward'.
        """

        xml_duration = xml_forward.find("duration")
        forward_duration = int(xml_duration.text)
        midi_ticks = forward_duration * (constants.STANDARD_PPQ / self.state.divisions)
        normalized = forward_duration * (self.state.lcm_divisions // self.state.divisions)
        seconds = (midi_ticks / constants.STANDARD_PPQ) * self.state.seconds_per_quarter
        self.state.time_position += seconds
        self.state.xml_position += normalized

        # self.guitarMeasure.append(copy.deepcopy(xml_forward))
        # self.guitarMeasureTabElements.append(copy.deepcopy(xml_forward))

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
                self.state.time_signature.denominator,
            )

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

                new_time_sig_fraction = Fraction(numerator, denominator)

                if new_time_sig_fraction == fractional_time_signature:
                    new_time_signature.numerator = fractional_time_signature.numerator
                    new_time_signature.denominator = (
                        fractional_time_signature.denominator
                    )

            # Insert a new time signature only if it does not equal the global
            # time signature.
            if pickup_measure or (
                self.time_signature is None
                and (fractional_time_signature != fractional_state_time_signature)
            ):
                new_time_signature.time_position = self.start_time_position
                new_time_signature.xml_position = self.start_xml_position
                self.time_signature = new_time_signature
                self.state.time_signature = new_time_signature
