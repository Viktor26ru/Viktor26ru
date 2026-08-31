from prototype_backend.messenger_service import MessengerService


def main() -> None:
    svc = MessengerService()

    alice = svc.bootstrap_user()
    bob = svc.bootstrap_user()

    invite = svc.create_invite(alice, ttl_seconds=600, max_uses=1)
    contact_id = svc.redeem_invite(invite.token, bob)

    chat_id = svc.create_or_get_direct_chat(alice, bob)
    msg_id = svc.send_message(chat_id, alice, ciphertext="ENCRYPTED:hello")

    print("alice:", alice)
    print("bob:", bob)
    print("invite:", f"{invite.token[:8]}… (redacted)")
    print("contact_id:", contact_id)
    print("chat_id:", chat_id)
    print("msg_id:", msg_id)
    print("alice_contacts:", svc.list_contacts(alice))
    print("bob_contacts:", svc.list_contacts(bob))


if __name__ == "__main__":
    main()
