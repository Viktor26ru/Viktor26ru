import unittest

from prototype_backend.messenger_service import MessengerService


class MessengerServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.svc = MessengerService()
        self.alice = self.svc.bootstrap_user()
        self.bob = self.svc.bootstrap_user()
        self.charlie = self.svc.bootstrap_user()

    def test_invite_single_use(self) -> None:
        invite = self.svc.create_invite(self.alice, ttl_seconds=600, max_uses=1)
        contact_id = self.svc.redeem_invite(invite.token, self.bob)
        self.assertTrue(contact_id.startswith("cnt_"))

        with self.assertRaisesRegex(ValueError, "INVITE_ALREADY_USED"):
            self.svc.redeem_invite(invite.token, self.charlie)

    def test_contacts_only_after_invite(self) -> None:
        self.assertEqual(self.svc.list_contacts(self.alice), [])
        invite = self.svc.create_invite(self.alice)
        self.svc.redeem_invite(invite.token, self.bob)

        self.assertEqual(self.svc.list_contacts(self.alice), [self.bob])
        self.assertEqual(self.svc.list_contacts(self.bob), [self.alice])

    def test_direct_chat_and_message(self) -> None:
        invite = self.svc.create_invite(self.alice)
        self.svc.redeem_invite(invite.token, self.bob)

        chat_id = self.svc.create_or_get_direct_chat(self.alice, self.bob)
        chat_id_again = self.svc.create_or_get_direct_chat(self.bob, self.alice)
        self.assertEqual(chat_id, chat_id_again)

        msg_id = self.svc.send_message(chat_id, self.alice, ciphertext="ENCRYPTED:text")
        self.assertTrue(msg_id.startswith("msg_"))


if __name__ == "__main__":
    unittest.main()
