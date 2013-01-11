#!/usr/bin/python

import binascii
import sys
import os
import re
from struct import pack, unpack

IPP_VERSION = "1.1"
IPP_PORT = 631

STATUS_CODES_SUCCESS = {"0x0000": "successful-ok", 
                        "0x0001": "successful-ok-ignored-or-substituted-attributes", 
                        "0x0002": "successful-ok-conflicting-attributes"}

STATUS_CODES_CLIENT_ERROR = {"0x0400": "client-error-bad-request", 
                             "0x0401": "client-error-forbidden", 
                             "0x0402": "client-error-not-authenticated", 
                             "0x0403": "client-error-not-authorized", 
                             "0x0404": "client-error-not-possible", 
                             "0x0405": "client-error-timeout", 
                             "0x0406": "client-error-not-found", 
                             "0x0407": "client-error-gone",
                             "0x0408": "client-error-request-entity-too-large", 
                             "0x0409": "client-error-request-value-too-long", 
                             "0x040A": "client-error-document-format-not-supported", 
                             "0x040B": "client-error-attributes-or-values-not-supported", 
                             "0x040C": "client-error-uri-scheme-not-supported", 
                             "0x040D": "client-error-charset-not-supported", 
                             "0x040E": "client-error-conflicting-attributes", 
                             "0x040F": "client-error-compression-not-supported", 
                             "0x0410": "client-error-compression-error", 
                             "0x0411": "client-error-document-format-error", 
                             "0x0412": "client-error-document-access-error"}

STATUS_CODES_SERVER_ERROR = {"0x0500": "server-error-internal-error", 
                             "0x0501": "server-error-operation-not-supported", 
                             "0x0502": "server-error-service-unavailable", 
                             "0x0503": "server-error-version-not-supported", 
                             "0x0504": "server-error-device-error", 
                             "0x0505": "server-error-temporary-error", 
                             "0x0506": "server-error-not-accepting-jobs", 
                             "0x0507": "server-error-busy", 
                             "0x0508": "server-error-job-canceled", 
                             "0x0509": "server-error-multiple-document-jobs-not-supported"}

class IPPResponseTCP :
  """Class for TCP responses to IPP requests."""
  #attributes_types = ("operation", "job", "printer", "unsupported", \
  #                                 "subscription", "event_notification")
  def __init__(self, data="", version=IPP_VERSION,
                              status_code=None, \
                              request_id=None, \
                              printattr=False, \
                              jobattr=False) :
    self._data = data
    self.parsed = False
    self.setVersion(version)
    self.setStatusCode(status_code)
    self.setRequestId(request_id)
    self.setPrintAttr(printattr)
    self.setJobAttr(jobattr)
    self.data = ""

    #for attrtype in self.attributes_types :
    #   setattr(self, "_%s_attributes" % attrtype, [[]])
    
    # Initialize tags    
    self.tags = [ None ] * 256 # by default all tags reserved
    
    self.tags[0x01] = "operation-attributes-tag"
    self.tags[0x02] = "job-attributes-tag"
    self.tags[0x03] = "end-of-attributes-tag"
    self.tags[0x04] = "printer-attributes-tag"
    self.tags[0x05] = "unsupported-attributes-tag"
    self.tags[0x21] = "integer"
    self.tags[0x22] = "boolean"
    self.tags[0x23] = "enum"
    self.tags[0x44] = "keyword"
    self.tags[0x45] = "uri"
    self.tags[0x46] = "uriScheme"
    self.tags[0x47] = "charset"
    self.tags[0x48] = "naturalLanguage"
    self.tags[0x49] = "mimeMediaType"
    
    # Reverse mapping to generate IPP messages
    self.tagvalues = {}
    for i in range(len(self.tags)) :
       value = self.tags[i]
       if value is not None :
         self.tagvalues[value] = i

  def setPrintAttr(self, newVal) :
    self.printAttr = newVal
    
  def setJobAttr(self, newVal) :
    self.jobAttr = newVal

  def setVersion(self, version) :
    """Sets the request's operation id."""
    if version is not None :
        try :
            self.version = [int(p) for p in version.split(".")]
        except AttributeError :
            if len(version) == 2 : # 2-tuple
                self.version = version
            else :    
                try :
                    self.version = [int(p) for p in str(float(version)).split(".")]
                except :
                    self.version = [int(p) for p in IPP_VERSION.split(".")]
      
  def setStatusCode(self, stcd) :        
    """Sets the request's operation id."""
    self.statusCode = stcd
      
  def setRequestId(self, reqid) :        
    """Sets the request's request id."""
    self.request_id = reqid.encode('hex')
    
  def generateResponse(self) :
    httprn = "0d0a"
    http = []
    # HTTP response code
    http.append("HTTP/1.1 200 OK".encode('hex'))
    http.append(httprn)
    # Server
    http.append("Server: Doopr".encode('hex'))
    http.append(httprn)
    # Transfer-Encoding
    http.append("Transfer-Encoding: chunked".encode('hex'))
    http.append(httprn)
    # Content-Type
    http.append("Content-Type: application/ipp".encode('hex'))
    http.append(httprn)
    # Cache-Control
    http.append("Cache-Control: max-age=3600, public".encode('hex'))
    http.append(httprn)
    http.append(httprn)
    # Chuck-Data
    # To get chunk size, we're going to have to generate the IPP header 
    # and determine how many bytes there are
    ipp = self.generateIPP()
    # which happens here. But, there's a twist: for some reason, the
    # length given in the header is given as a hex string, not just a 
    # hex value -- i.e. it'll be 0x0041 but they'll want "30303431" 
    stringifylength = "{0:08X}".format(int(hex(len(ipp) / 2), 16))
    chunklength = ""
    for c in stringifylength :
        chunklength += "".join("{0:02X}".format(int(hex(ord(c)), 16)))
    http.append(chunklength)
    http.append(httprn)
    http.append(ipp)
    http.append(httprn)
    http.append("{0:02X}".format(int("0", 16)))
    http.append(httprn)
    http.append(httprn)
    return "".join(http)
    
  def generateIPP(self) :
    """Generates the hex for the response (WIP)."""
    if self.statusCode in STATUS_CODES_SUCCESS :
      return STATUS_CODES_SUCCESS[self.statusCode]
    elif self.statusCode in STATUS_CODES_CLIENT_ERROR or self.statusCode in STATUS_CODES_SERVER_ERROR :
      packet = []
      """All of the IPP Response REQUIRED attributes are constructed here"""
      packet.append("{0:02X}".format(self.version[0]))
      packet.append("{0:02X}".format(self.version[1]))
      packet.append("{0:04X}".format(int(self.statusCode, 16)))
      packet.append("{0:08X}".format(int(self.request_id, 16)))
      packet.append("{0:02X}".format(self.tagvalues["operation-attributes-tag"]))
      packet.append("{0:02X}".format(self.tagvalues["charset"]))
      packet.append("{0:04X}".format(int(hex(len("attributes-charset")), 16)))
      packet.append("attributes-charset".encode('hex'))
      packet.append("{0:04X}".format(int(hex(len("us-ascii")), 16)))
      packet.append("us-ascii".encode('hex'))
      packet.append("{0:02X}".format(self.tagvalues["naturalLanguage"]))
      packet.append("{0:04X}".format(int(hex(len("attributes-natural-language")), 16)))
      packet.append("attributes-natural-language".encode('hex'))
      packet.append("{0:04X}".format(int(hex(len("en-us")), 16)))
      packet.append("en-us".encode('hex'))
      """If we're responding with the printer attributes data, construct here"""
      if self.printAttr : 
        packet.append("{0:02X}".format(self.tagvalues["printer-attributes-tag"]))
        packet.append("{0:02X}".format(self.tagvalues["enum"])) # Tag
        packet.append("{0:04X}".format(int(hex(len("printer-state")), 16))) # Name length
        packet.append("printer-state".encode('hex')) # Name
        packet.append("{0:04X}".format(int("0x0004", 16))) # Value length
        packet.append("{0:08X}".format(int("0x00000003", 16))) # Value
        packet.append("{0:02X}".format(self.tagvalues["keyword"])) # Tag
        packet.append("{0:04X}".format(int(hex(len("printer-state-reasons")), 16))) # Name length
        packet.append("printer-state-reasons0".encode('hex')) # Name
        packet.append("{0:04X}".format(int(hex(len("none")), 16))) # Value length
        packet.append("none".encode('hex')) # Value
        packet.append("{0:02X}".format(self.tagvalues["mimeMediaType"])) # Tag
        packet.append("{0:04X}".format(int(hex(len("document-format-supported")), 16))) # Name length
        packet.append("document-format-supported".encode('hex')) # Name
        packet.append("{0:04X}".format(int(hex(len("text/plain")), 16))) # Value length
        packet.append("text/plain".encode('hex')) # Value
        packet.append("{0:02X}".format(self.tagvalues["boolean"]));
        packet.append("{0:04X}".format(int(hex(len("printer-is-accepting-jobs")), 16))) # Name length
        packet.append("printer-is-accepting-jobs".encode('hex')) # Name
        packet.append("{0:04X}".format(int("0x0001", 16))) # Value length
        if self.statusCode == "0x0506" : 
          packet.append("{0:02X}".format(int("0", 16))) # Value
        else :
          packet.append("{0:02X}".format(int("1", 16)))
      packet.append("{0:02X}".format(self.tagvalues["end-of-attributes-tag"]))
      return "".join(packet)
    else :
      return "STATUS CODE NOT RECOGNIZED"

class IPPResponseUDP :
  """Class for UDP responses to IPP requests."""
  def __init__ (self, 
                reqoid=None, 
                requestid=None, 
                requestidlength=None, 
                pdutype=None, 
                version=None,
                dstip=None) :
    self.reqoid = reqoid if reqoid != None else ""
    self.requestid = requestid if requestid != None else "1"
    self.pdutype = pdutype if pdutype != None else 0xA0
    self.requestidlength = requestidlength if requestidlength != None else "1"
    self.version = version if version != None else 0x00
    self.dstip = dstip if dstip != None else ""
    
    self.ids = {"integer":0x02, 
                "bit-string":0x03,
                "octet-string":0x04, 
                "null":0x05, 
                "object-identifier":0x06,
                "sequence":0x30, 
                "ip-address":0x40,
                "counter":0x41,
                "gauge":0x42,
                "timeticks":0x43,
                "opaque":0x44,
                "nsap-address":0x45,
                "get-request":0xA0,
                "get-next-request":0xA1, 
                "get-response":0xA2, 
                "set-request":0xA3,
                "trap-pdu":0xA4}
    
    self.idsv2 = {"counter32":0x41,
                  "gauge32":0x42,
                  "counter64":0x46,
                  "uinteger32":0x47,
                  "response-pdu":0xA2,
                  "get-bulk-request":0xA5,
                  "inform-request":0xA6,
                  "snmpv2-trap":0xA7}
    
  def generateResponse(self) :
    """ 
      The if statements here don't really do anything at the moment,
      but if further research reveals a difference between get-request
      and get-next-request pdu types, it'll come in handy
    """
    if int(self.pdutype, 16) == self.ids["get-request"] :
      packet = []
      head = []
      snmpversion = []
      snmpversion.append("{0:02X}".format(self.ids["integer"]))
      snmpversion.append("{0:02X}".format(int("1", 16)))
      snmpversion.append("{0:02X}".format(int("0", 16)))
      head.append("".join(snmpversion))
      snmpcommstring = []
      snmpcommstring.append("{0:02X}".format(self.ids["octet-string"]))
      snmpcommstring.append("{0:02X}".format(int(hex(len("public")), 16)))
      snmpcommstring.append("public".encode('hex'))
      head.append("".join(snmpcommstring))
      head = "".join(head)
      pdu = self.generatePDU()
      packet.append("{0:02X}".format(self.ids["sequence"]))
      packet.append("{0:02X}".format(int(hex((len(head) + len(pdu)) / 2), 16)))
      packet.append(head)
      packet.append(pdu)
      return "".join(packet)
    elif int(self.pdutype, 16) == self.ids["get-next-request"] :
      packet = []
      head = []
      snmpversion = []
      snmpversion.append("{0:02X}".format(self.ids["integer"]))
      snmpversion.append("{0:02X}".format(int("1", 16)))
      snmpversion.append("{0:02X}".format(int("0", 16)))
      head.append("".join(snmpversion))
      snmpcommstring = []
      snmpcommstring.append("{0:02X}".format(self.ids["octet-string"]))
      snmpcommstring.append("{0:02X}".format(int(hex(len("public")), 16)))
      snmpcommstring.append("public".encode('hex'))
      head.append("".join(snmpcommstring))
      head = "".join(head)
      pdu = self.generatePDU()
      packet.append("{0:02X}".format(self.ids["sequence"]))
      packet.append("{0:02X}".format(int(hex((len(head) + len(pdu)) / 2), 16)))
      packet.append(head)
      packet.append(pdu)
      return "".join(packet)
    else :
      return "00"

  def generatePDU(self) :
    pdu = []
    reqid = []
    reqid.append("{0:02X}".format(self.ids["integer"]))
    reqid.append("{0:02X}".format(int(str(self.requestidlength), 16)))
    reqid.append("{0:02X}".format(int(hex(self.requestid), 16)))
    reqid = "".join(reqid)
    error = []
    error.append("{0:02X}".format(self.ids["integer"]))
    error.append("{0:02X}".format(int("1", 16)))
    error.append("{0:02X}".format(int("0", 16)))
    error = "".join(error)
    errindex = []
    errindex.append("{0:02X}".format(self.ids["integer"]))
    errindex.append("{0:02X}".format(int("1", 16)))
    errindex.append("{0:02X}".format(int("0", 16)))
    errindex = "".join(errindex)
    pdu.append("{0:02X}".format(self.ids["get-response"]))
    varbindlist = self.generateVarbindList()
    pdu.append("{0:02X}".format(int(hex((len(reqid) + len(error) + len(errindex) + len(varbindlist)) / 2), 16)))
    pdu.append(reqid)
    pdu.append(error)
    pdu.append(errindex)
    pdu.append(varbindlist)    
    return "".join(pdu)
    
  def generateVarbindList(self) :
    #Need to find a fake MIB to copy and present attributes from
    varbind = self.generateVarbind()
    varbindlist = []
    varbindlist.append("{0:02X}".format(self.ids["sequence"]))
    varbindlist.append("{0:02X}".format(int(hex(len(varbind) / 2), 16)))
    varbindlist.append(varbind)
    return "".join(varbindlist)
    
  def generateVarbind(self) :
    oid = []
    oid.append("{0:02X}".format(self.ids["object-identifier"]))
    oid.append("{0:02x}".format(int(hex((len(self.reqoid) / 2)), 16)))
    oid.append(self.reqoid)
    oid = "".join(oid)
    value = []
    mib = self.generateMIB()
    value.append("{0:02X}".format(self.ids["object-identifier"]))
    value.append("{0:02X}".format(int(hex(len(mib) / 2), 16)))
    value.append(mib)
    value = "".join(value)
    varbind = []
    varbind.append("{0:02X}".format(self.ids["sequence"]))
    varbindlength = len(oid) + len(value)
    varbind.append("{0:02X}".format(int(hex(varbindlength / 2), 16)))
    varbind.append(oid)
    varbind.append(value)
    return "".join(varbind)
  
  def generateMIB(self) :
    # This method is going to require a refactor
    # Essentially, depending on the structure of the reqoid 
    # the script is going to have to determine what values are 
    # being request, and then proffer them in the correct format
    """
      mib = ""
      # hardcode a lexmark printer since we have one around 
      # and I found a mib structure for it
      if re.match("2b06010201", self.reqoid) :
        # If this string matches, that means the request was for
        # something within the 1.3.6.1.2 MIB subtree, which 
        # corresponds to system-specific information and 
        # identifiers
        mib = "2b06010201"
        mib += self.determineMIBSystemValue(self.reqoid[10:])
      elif re.match("2b06010401", self.reqoid) :
        # This corresponds to a response for a particular variable
        # within our "printer's" MIB, and as we're using lexmark, 
        # the string translates to 1.3.6.1.4.1.641
        # Any appended string is going to correspond to more specific
        # printer things like toner color, etc.
        mib = "2b060104018501"
        mib += self.determineMIBHostValue(self.reqoid[14:])
      else :
        mib = ""
      return mib
    """
    return "2b0601020119030105"
  
  def matchOidToResponse(self) :
    f = open(ip + '.txt', 'r')
    match = f.readlines()
    res = []
    for line in match :
      split = line.split(':')
      if split[0] == self.reqoid :
        res.append("{0:02X}".format(self.ids[split[1]]))
        res.append("{0:02X}".format())
  
  def determineMIBSystemValue(self, oid) :
    mibtreepath = []
    returnmib = []
    sys.stderr.write("oid : " + oid + "\n")
    sys.stderr.write("len(oid) : " + str(len(oid)) + "\n")
    for i in xrange(0, len(oid), 2) :
      mibtreepath.append(str(oid[i:i+2]))
    # response should be 1.3.6.1.2.1.25.3.1.5
    # have 1.3.6.1.2
    if mibtreepath[0] == "19" and mibtreepath[1] == "02" : 
      returnmib.append("19030105") 
    elif mibtreepath[0] == "19" and mibtreepath[1] == "03" :
      # Lexmark T620 NM820C50 541.019
      returnmib.append("Lexmark T620 NM820C50 541.019".encode('hex'))
    return "".join(returnmib)

  def determineMIBHostValue(self, oid) :
    mibtreepath = []
    sys.stderr.write("oid : " + oid + "\n")
    sys.stderr.write("len(oid) : " + str(len(oid)) + "\n")
    for i in xrange(0, len(oid), 2) :
      mibtreepath.append(str(oid[i:i+2]))
    return ""

"""if __name__ == "__main__" :
  parser = argparse.ArgumentParser()
  parser.add_argument('-s', '--status-code', help='What IPP Response status code to return', required=True)
  parser.add_argument('-r', '--request-id', help='The IPP Request\'s request ID', required=True)
  parser.add_argument('-p', '--printer-attr', help='If used, the response will include the printer-attributes-tag section with bogus data')
  parser.add_argument('-j', '--job-attr', help='If used, the response will include the job-attributes-tag section with bogus data (NOT USED)')
  args = parser.parse_args()
  
  statuscode = args.status_code
  requestid = args.request_id
  if args.job_attr != None :
    jobattrarg = True
  else :
    jobattrarg = False
  if args.printer_attr != None :
    printattrarg = True
  else :
    printattrarg = False
    
  req = IPPResponseTCP(status_code=statuscode, request_id=requestid, printattr=printattrarg, jobattr=jobattrarg)
  print req.generateResponse()"""
