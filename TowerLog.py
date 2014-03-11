__author__ = 'ghoti'

import evelink.api
import evelink.char
import evelink.eve
import sys
import logging
import getpass
from optparse import OptionParser
import datetime
import ConfigParser

import sleekxmpp

# Python versions before 3.0 do not use UTF-8 encoding
# by default. To ensure that Unicode is handled properly
# throughout SleekXMPP, we will set the default encoding
# ourselves to UTF-8.
if sys.version_info < (3, 0):
    reload(sys)
    sys.setdefaultencoding('utf8')
else:
    raw_input = input

#DIDNT WANT THAT QUICK STARTUP TIME ANYWAY JESUS FUCK
moons = {}
with open('MoonData.txt') as f:
    for line in f:
        (key, val) = line.split(',')
        moons[int(key.strip('\xef\xbb\xbf'))] = val.strip('\n')

class MUCBot(sleekxmpp.ClientXMPP):

    """
    A simple SleekXMPP bot that will greets those
    who enter the room, and acknowledge any messages
    that mentions the bot's nickname.
    """

    def __init__(self, jid, password, room, nick):
        sleekxmpp.ClientXMPP.__init__(self, jid, password)

        self.room = room
        self.nick = nick

        #HUEHUEHUE
        self.config = ConfigParser.ConfigParser()
        self.config.readfp(open('character.cfg'))
        self.jabberpass = self.config.get('jabber', 'password')
        self.charactername = self.config.get('api', 'CharacterName')
        self.keyid = self.config.get('api', 'keyid')
        self.vcode = self.config.get('api', 'vcode')

        # The session_start event will be triggered when
        # the bot establishes its connection with the server
        # and the XML streams are ready for use. We want to
        # listen for this event so that we we can initialize
        # our roster.
        self.add_event_handler("session_start", self.start)

        # The groupchat_message event is triggered whenever a message
        # stanza is received from any chat room. If you also also
        # register a handler for the 'message' event, MUC messages
        # will be processed by both handlers.
        self.add_event_handler("groupchat_message", self.muc_message)

        # The groupchat_presence event is triggered whenever a
        # presence stanza is received from any chat room, including
        # any presences you send yourself. To limit event handling
        # to a single room, use the events muc::room@server::presence,
        # muc::room@server::got_online, or muc::room@server::got_offline.
        self.add_event_handler("muc::%s::got_online" % self.room,
                               self.muc_online)



        self.lastnotification = 'There are no previous notifications'


    #A wonky 'wish i was a switch case' dict to hold our important and spammy notifications
    #Later these will point to functions instead of silly strings when we call notificationtexts
    #We use functions as dictionary values so that later when we get notification details we can handle
    #different responses from the api for each type of notification
    def noteid(self):
        return{
            14:self.bounty,
            16:self.application,
            17:self.denial,
            18:self.acceptance,
            45:self.anchoralert,
            46:self.vulnstruct,
            47:self.invulnstruct,
            48:self.sbualert,
            76:self.posfuel,
            86:self.tcualert,
            87:self.sbushot,
            88:self.ihubalert,
            93:self.pocoalert,
            94:self.pocorf,
            96:self.fwwarn,
            97:self.fwkick,
            128:self.joinfweddit #join note is same as app note with different id hue
        }
    def bounty(self, id):
        return 'a bounty was claimed!'
    def application(self, id):
        app = self.gettext(id)
        eve = evelink.eve.EVE()
        name = eve.character_name_from_id(app[id]['charID'])
        return '%s has apped to Fweddit!' % name[0]
        #return 'Someone apped to fweddit!'
    def denial(self, id):
        return 'Someone was denied into fweddit!'
    def acceptance(self, id):
        return 'Someone was accepted into fweddit!'
    def anchoralert(self, id):
        return 'Something was anchroed in our sov!'
    def vulnstruct(self, id):
        return 'Something went vulnerable in our sov!'
    def invulnstruct(self, id):
        return 'Something went invulnerable in our sov!'
    def sbualert(self, id):
        return 'Someone anchored an SBU in our sov!'
    def posfuel(self, id):
        #I HAS NO IDEA WHAT INFO IS USEFUL HERE
        pos = self.gettext(id)
        return 'THE TOWER AT %s NEEDS FUELS PLS - %d remaining' % (moons[pos[id]['moonID']], pos[id]['- quantity'])
    def tcualert(self, id):
        return 'Someone shot a TCU we own!'
    def sbushot(self, id):
        return 'Someone shot an SBU we own!'
    def ihubalert(self, id):
        return 'Someone shot an IHUB we own!'
    def pocoalert(self, id):
        return 'Someone shot a POCO we own!'
    def pocorf(self, id):
        return 'Someone reinforced a POCO we own!'
    def fwwarn(self, id):
        return 'We are in danger of being kicked from FW!'
    def fwkick(self, id):
        return 'We have been kicked from FW! RIP!'
    def joinfweddit(self, id):
        app = self.gettext(id)
        eve = evelink.eve.EVE()
        name = eve.character_name_from_id(app[id]['charID'])
        return '%s has joined Fweddit!' % name[0]

    def gettext(self,notificationid):
        api = evelink.api.API(api_key=(self.keyid, self.vcode))
        eve = evelink.eve.EVE()
        id = eve.character_id_from_name(self.charactername)
        char = evelink.char.Char(char_id=id, api=api)

        notes = char.notification_texts(notification_ids=(notificationid))
        return notes[0]


    def start(self, event):
        """
        Process the session_start event.

        Typical actions for the session_start event are
        requesting the roster and broadcasting an initial
        presence stanza.

        Arguments:
            event -- An empty dictionary. The session_start
                     event does not provide any additional
                     data.
        """
        self.get_roster()
        self.send_presence()
        self.plugin['xep_0045'].joinMUC(self.room,
                                        self.nick, password=self.jabberpass,
                                        # If a room password is needed, use:
                                        # password=the_room_password,
                                        wait=True)


        # Call the tower method to check the api, and announce anything recent (being 30 minutes
        # due to ccp api limitations, then schedule the same job to be ran every 30 minutes (give or take 30 seconds)

        self.towers()
        self.schedule('towertimer', 1800, self.towers, repeat=True)


    def muc_message(self, msg):
        """
        Process incoming message stanzas from any chat room. Be aware
        that if you also have any handlers for the 'message' event,
        message stanzas may be processed by both handlers, so check
        the 'type' attribute when using a 'message' event handler.

        Whenever the bot's nickname is mentioned, respond to
        the message.

        IMPORTANT: Always check that a message is not from yourself,
                   otherwise you will create an infinite loop responding
                   to your own messages.

        This handler will reply to messages that mention
        the bot's nickname.

        Arguments:
            msg -- The received message stanza. See the documentation
                   for stanza objects and the Message stanza to see
                   how it may be used.
        """

        if msg['mucnick'] != self.nick and self.nick in msg['body']:
            self.send_message(mto=msg['from'].bare,
                              mbody="I heard that, %s." % msg['mucnick'],
                              mtype='groupchat')

        # Proof of concept command testing - might be used later for repeating previous alerts, etc
        if msg['mucnick'] != self.nick and '!testing' in msg['body']:
            self.send_message(mto=msg['from'].bare,
                              mbody='%s: Confirming a command works proper' % msg['mucnick'],
                              mtype='groupchat')

        if msg['mucnick'] != self.nick and '!lastmsg'  in msg['body']:
            self.send_message(mto=msg['from'].bare,
                              mbody='%s: %s' % (msg['mucnick'], self.lastnotification),
                              mtype='groupchat')


    def towers(self):
        '''
        We call the CCP API once every thirty minutes for any new notifications.  We don't care if it's beed read.
        If the notification is from the past 30 minutes (a limitation of CCP's cache system) then we create a
        message with the info (TODO: Call notificationtexts to get notification info - who, what, where, etc) and
        send it to the channel we are connected to.  (POSSIBLE TODO: Connect to multiple rooms to announce different
        information to different auth groups)
        '''

        # Build a basic message header with hardcoded info.  This is probably bad.
        mess = sleekxmpp.Message()
        #mess['id'] = 'purple'
        #mess['type'] = 'groupchat'
        mess['from'] = 'leadership@conference.j4lp.com/AllianceBot'
        #mess['to'] = 'chainsaw_mcginny@j4lp.com'

        #hard coding api's - also probably bad
        api = evelink.api.API(api_key=(self.keyid, self.vcode))
        eve = evelink.eve.EVE()
        id = eve.character_id_from_name(self.charactername)
        char = evelink.char.Char(char_id=id, api=api)
        notes = char.notifications()

        # CCP sends us the past 200 notifications, we only care about the most recent (30 minutes)
        for notificationID in notes[0]:
            now = datetime.datetime.now()

            timesent = notes[0][notificationID]['timestamp']
            #timesent = datetime.datetime.strptime(timesent,'%Y-%m-%d %H:%M:%S')
            timesent = datetime.datetime.fromtimestamp(timesent)
            #print timesent, now-datetime.timedelta(minutes=60)
            if timesent > now-datetime.timedelta(minutes=30):
                sendme = self.noteid().get(notes[0][notificationID]['type_id'], '')
                if sendme:
                    message = sendme(notificationID)
                    self.lastnotification = message
                    self.send_message(mto=mess['from'].bare, mbody=message, mtype='groupchat')

    def muc_online(self, presence):
        """
        Process a presence stanza from a chat room. In this case,
        presences from users that have just come online are
        handled by sending a welcome message that includes
        the user's nickname and role in the room.

        Arguments:
            presence -- The received presence stanza. See the
                        documentation for the Presence stanza
                        to see how else it may be used.
        """
        #WE DONT DO SHIT WHEN PEOPLE LOG ON
        pass
        #if presence['muc']['nick'] != self.nick:
        #    self.send_message(mto=presence['from'].bare,
        #                      mbody="Hello, %s %s" % (presence['muc']['role'],
        #                                              presence['muc']['nick']),
        #                      mtype='groupchat')


if __name__ == '__main__':
    # Setup the command line arguments.
    optp = OptionParser()

    # Output verbosity options.
    optp.add_option('-q', '--quiet', help='set logging to ERROR',
                    action='store_const', dest='loglevel',
                    const=logging.ERROR, default=logging.INFO)
    optp.add_option('-d', '--debug', help='set logging to DEBUG',
                    action='store_const', dest='loglevel',
                    const=logging.DEBUG, default=logging.INFO)
    optp.add_option('-v', '--verbose', help='set logging to COMM',
                    action='store_const', dest='loglevel',
                    const=5, default=logging.INFO)

    # JID and password options.
    optp.add_option("-j", "--jid", dest="jid",
                    help="JID to use")
    optp.add_option("-p", "--password", dest="password",
                    help="password to use")
    optp.add_option("-r", "--room", dest="room",
                    help="MUC room to join")
    optp.add_option("-n", "--nick", dest="nick",
                    help="MUC nickname")

    opts, args = optp.parse_args()

    # Setup logging.
    logging.basicConfig(level=opts.loglevel,
                        format='%(levelname)-8s %(message)s')

    if opts.jid is None:
        opts.jid = raw_input("Username: ")
    if opts.password is None:
        opts.password = getpass.getpass("Password: ")
    if opts.room is None:
        opts.room = raw_input("MUC room: ")
    if opts.nick is None:
        opts.nick = raw_input("MUC nickname: ")

    # Setup the MUCBot and register plugins. Note that while plugins may
    # have interdependencies, the order in which you register them does
    # not matter.
    xmpp = MUCBot(opts.jid, opts.password, opts.room, opts.nick)
    xmpp.register_plugin('xep_0030') # Service Discovery
    xmpp.register_plugin('xep_0045') # Multi-User Chat
    xmpp.register_plugin('xep_0199') # XMPP Ping


    # Connect to the XMPP server and start processing XMPP stanzas.
    if xmpp.connect():
        # If you do not have the dnspython library installed, you will need
        # to manually specify the name of the server if it does not match
        # the one in the JID. For example, to use Google Talk you would
        # need to use:
        #
        # if xmpp.connect(('talk.google.com', 5222)):
        #     ...
        xmpp.process(block=True)
        print("Done")
    else:
        print("Unable to connect.")
