class Technical(object):
  """Internal representation of a MusicXML Notations' Technical properties.
  
  This represents the following technical notation symbols:

  1) string
  2) fret
  3) pluck
  4) hammer-on
  5) pull-off

  """

  def __init__(self, xml_technical=None):
    self.xml_technical = xml_technical
    self.fret = None
    self.string = None
    self.pluck = None
    self.is_hammered_on = False
    self.is_pulled_off = False
    self.fingering = None

  def parse_technical(self, xml_technical):
    """Parse the MusicXML <Technical> element."""
    self.xml_technical = xml_technical
    if self.xml_technical is not None:
      technicals = list(self.xml_technical)
      for child in technicals:
        if child.tag == 'string':
          self.string = int(child.text)
        elif child.tag == 'fret':
          self.fret = int(child.text)
        elif child.tag == 'pluck':
          self.pluck = child.text
        elif child.tag == 'hammer-on':
            if child.attrib['type'] == 'stop':
                self.is_hammered_on = True
        elif child.tag == 'pull-off':
            if child.attrib['type'] == 'stop':
                self.is_pulled_off = True
        elif child.tag == 'fingering':
            try:
              self.fingering = int(child.text)
            except:
              self.fingering = None