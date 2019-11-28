import re

from lxml import etree
from odoo import models
from odoo.addons.account_payment_return_import_sepa_pain.wizard.pain_parser \
    import PainParser


class Pain002Parser(models.AbstractModel, PainParser):
    _name = 'account.pain002.parser'

    def parse_transaction(self, ns, node, transaction):
        """Parse transaction (entry) node."""
        self.add_value_from_node(
            ns, node, './ns:OrgnlEndToEndId', transaction,
            'reference'
        )
        self.add_value_from_node(
            ns, node, './ns:TxSts', transaction,
            'status'
        )
        self.add_value_from_node(
            ns, node, './ns:StsRsnInf/ns:Rsn/ns:Cd', transaction,
            'reason_code'
        )
        self.add_value_from_node(
            ns, node, './ns:StsRsnInf/ns:AddtlInf', transaction,
            'reason'
        )
        details_node = node.xpath(
            './ns:OrgnlTxRef', namespaces={'ns': ns})
        if details_node:
            self.parse_transaction_details(ns, details_node[0], transaction)
        transaction['raw_import_data'] = etree.tostring(node)

        transaction['amount'] = self.env['bank.payment.line']\
            .search([('name', '=', transaction['reference'])]).amount_currency
        return transaction

    def check_version(self, ns, root):
        """Validate validity of pain 002 CH Report file."""
        # Check wether it is SEPA Direct Debit Unpaid Report at all:
        re_pain = re.compile(
            r'(^http://www.six-interbank-clearing.com/de/pain.)'
        )
        if not re_pain.search(ns):
            raise ValueError('no pain: ' + ns)
        # Check wether version 002.001.03.ch.02:
        re_pain_version = re.compile(
            r'(^urn:iso:std:iso:20022:tech:xsd:pain.002.001.03'
            r'|pain.002.001.03.ch.02)'
        )
        if not re_pain_version.search(ns):
            raise ValueError('no PAIN.002.001.03.ch.02: ' + ns)
        # Check GrpHdr element:
        root_0_0 = root[0][0].tag[len(ns) + 2:]  # strip namespace
        if root_0_0 != 'GrpHdr':
            raise ValueError('expected GrpHdr, got: ' + root_0_0)

    def parse(self, data):
        """Parse a pain.002.001.03 file."""
        try:
            root = etree.fromstring(data, parser=etree.XMLParser(recover=True))
        except etree.XMLSyntaxError:
            # ABNAmro is known to mix up encodings
            root = etree.fromstring(data.decode('iso-8859-15').encode('utf-8'))
        if root is None:
            raise ValueError(
                'Not a valid xml file, or not an xml file at all.')
        ns = root.tag[1:root.tag.index("}")]
        self.check_version(ns, root)
        for node in root:
            data = super().parse_payment_return(ns, node)

            self.add_value_from_node(ns, node,
                                     './ns:OrgnlGrpInfAndSts/ns:OrgnlMsgId',
                                     data, 'order_name')

            if 'account_number' not in data:
                payment_order = self.env['account.payment.order'] \
                    .search([('name', '=', data['order_name'])])
                data['account_number'] = payment_order \
                    .company_partner_bank_id.acc_number

            return data
