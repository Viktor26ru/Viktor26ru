import { defineSchedule } from "@cursor/bdk/schedules";
import { flushPendingMail } from "../lib/email.js";

export default defineSchedule({
  cron: "10 * * * *",
  async run({ host }) {
    await flushPendingMail(host);
  },
});
