#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# Web.de Mail-App Parser
# Malte Woischwill, BKI Flensburg K9
#
# Versionshistorie:
# siehe *-versions.txt
#
from physical import *
import SQLiteParser
from System.Convert import IsDBNull
import re

class web_de_parser(object):
    '''
    WEB.DE Mail & Cloud Parser
    Parses mails and accounts
    '''

    def __init__(self):
        self.APP_NAME = 'WEB.DE Mail & Cloud'
        self.results = []
        print("##############################")
        print("# " + self.APP_NAME + " Parser gestartet")

        self.Identity_node = self.__find_db("identity")
        if not self.Identity_node:
            print("# Keine Web.de Datenbank gefunden")
            return
        self.MailDB_node = self.__find_db("MailDB")
        self.Mail_room_node = self.__find_db("mail_room")
        self.mail_db = SQLiteParser.Database.FromNode(self.MailDB_node)
        self.mail_room_db = SQLiteParser.Database.FromNode(self.Mail_room_node)
        self.identity_db = SQLiteParser.Database.FromNode(self.Identity_node)

    def parse(self):
        print("### Parsen der DBs")
        mails = []
        for rec in self.mail_room_db["mail"]:
            mails.append(rec)
        folder = []
        for rec in self.mail_room_db["folder"]:
            folder.append(rec)
        attachments = []
        for rec in self.mail_room_db["attachment"]:
            attachments.append(rec)
        accounts = []
        for rec in self.identity_db["Identity"]:
            accounts.append(rec)
        # Konstruieren von PA Objekten aus Daten
        ############################################
        print("### Kreieren von PA Objekten")
        print("### UserAccounts erstellen")
        for acc in accounts:
            new_acc = self.generate_account(acc["email"], self.APP_NAME, acc["entryDate"],
                                  acc["name"].Value)
            new_acc.Source.Value = self.Identity_node.FullPath
            self.results.append(new_acc)

        print("### Mails Erstellen")
        temp_len = len(self.results)
        known_from_parties = {}
        known_to_parties = {}
        for mail in mails:
            if IsDBNull(mail["subject"].Value) and IsDBNull(mail["textbody"].Value) and IsDBNull(mail["email_from"].Value):
                continue
            to_parties, cc_parties, bcc_parties = [], [], []
            mail_folder = next((item["name"] for item in folder if item["_id"].Value == mail["folderId"].Value), None)
            known_from_parties[mail["email_from"]] = self.generate_party(mail["email_from"], mail["date"],
                                                                               mail["sender"].Value, PartyRole.From)
            known_to_parties[mail["email_to"]] = self.generate_party(mail["email_to"], mail["date"],
                                                                           next((item["name"].Value for item in accounts
                                                                                 if item["email"].Value ==
                                                                                 mail["email_to"].Value), None), PartyRole.To)
            to_parties.append(known_to_parties[mail["email_to"]])
            if mail["bcc"].Value:
                bcc_parties.append(self.generate_party(mail["bcc"], mail["date"]))
            if mail["cc"].Value:
                cc_parties.append(self.generate_party(mail["cc"], mail["date"]))
            new_mail = self.generate_mail(mail_folder, known_from_parties[mail["email_from"]], to_parties, mail["subject"], mail["textbody"],
                                          mail["isUnread"], mail["date"],[], cc_parties, bcc_parties,
                                          next((item["email"] for item in accounts if item["accountId"].Value == mail["account_id"].Value), None))
            self.results.append(new_mail)
        print("### Gefundene Accounts: " + str(temp_len))
        print("### Gefundene Mails: " + str(len(self.results)-temp_len))
        return self.results

    def generate_mail(self, mail_folder, mail_from_party, mail_to_parties, mail_subject, mail_body, mail_status,
                      mail_timestamp, mail_attachments, mail_cc_parties, mail_bcc_parties, mail_account):
        mail = Email()
        mail.Source.Value = self.APP_NAME
        mail.Deleted = DeletedState.Intact
        if not IsDBNull(mail_folder.Value):
            mail.Folder.SetValue(mail_folder.Value)
        mail.From.SetValue(mail_from_party)
        mail.To.AddRange(mail_to_parties)
        if not IsDBNull(mail_subject.Value):
            mail.Subject.SetValue(mail_subject.Value)
        if not IsDBNull(mail_body.Value):
            mail.Body.SetValue(mail_body.Value)
        if not IsDBNull(mail_timestamp.Value):
            mail.TimeStamp.Value = TimeStamp.FromUnixTime(mail_timestamp.Value/1000)
        mail.Attachments.AddRange(mail_attachments)
        mail.Cc.AddRange(mail_cc_parties)
        mail.Bcc.AddRange(mail_bcc_parties)
        if not IsDBNull(mail_status.Value):
            mail.Status.Value = MessageStatus.Unread if mail_status else MessageStatus.Read
        if not IsDBNull(mail_account.Value):
            mail.Account.Value = mail_account.Value
        return mail

    def generate_account(self, ac_username, ac_servicetype, ac_timecreated, ac_name=""):
        account = UserAccount()
        account.Deleted = DeletedState.Intact
        account.Username.SetValue(ac_username.Value)
        account.ServiceType.SetValue(ac_servicetype)
        account.TimeCreated.SetValue(self.get_TimeStamp(ac_timecreated))
        account.Name.SetValue(ac_name)
        return account

    def modify_party_ident(self, party):
        if IsDBNull(party.Value):
            return None
        elif party.Value.find('<') >= 0:
            start = party.Value.find('<') + 1
            end = party.Value.find('>')
            return party.Value[start:end]
        else:
            return party.Value

    def generate_party(self, party_ident, party_delivereddate, party_name="", party_role=PartyRole.General):
        party = Party()
        party.Deleted = DeletedState.Intact
        party.Identifier.Value = self.modify_party_ident(party_ident)
        if not IsDBNull(party_name) and party_name:
            end = party_ident.Value.find('<')
            if end > 0:
                party.Name.Value = party_ident.Value[0:end]
            elif party_name.find('@') >= 0:
                party.Name.Value = party_name
        if not IsDBNull(party_role):
            party.Role.Value = party_role
        if not IsDBNull(party_delivereddate):
            party.DateDelivered.Value = TimeStamp.FromUnixTime(party_delivereddate.Value/1000)
        return party

    def get_TimeStamp(self, timestamp):
        if len(timestamp.Value) == 0:
            return None
        ts = timestamp.Value.replace("T", "-").replace("Z", "").replace(":", "-").split("-")
        return TimeStamp(DateTime(int(ts[0]), int(ts[1]), int(ts[2]), int(ts[3]), int(ts[4]), int(ts[5])), True)


    def __find_db(self, name):
        print('### suche nach ' + name + '-db]')

        re_journal = re.compile(r'(-journal){1}(_?[0-9]*)(?=$)')
        re_shm = re.compile(r'(-shm){1}(_?[0-9]*)(?=$)')
        re_wal = re.compile(r'(-wal){1}(_?[0-9]*)(?=$)')
        result = []
        for fs in ds.FileSystems:
            for node in fs.Search('/de.web.mobile.android.mail/databases/' + name + '*'):
                if re_journal.search(node.Name):
                    continue
                elif re_shm.search(node.Name):
                    continue
                elif re_wal.search(node.Name):
                    continue
                else:
                    result = node
        print("### " + name + " Datenbank gefunden")
        return result


# calling the parser for results
results = web_de_parser().parse()

# adding the results to the tree view
ds.Models.AddRange(results)
