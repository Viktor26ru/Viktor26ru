import { defineEval } from "@cursor/bdk/evals";

export default defineEval({
  tags: ["smoke"],
  cases: [
    {
      id: "record-problem",
      description: "Фиксирует проблему заказчика и не закрывает этап без остальных пунктов.",
      async test(t) {
        await t.send("Чат eval-1. Заказчик сказал: счета теряются между почтой и таблицей, из-за этого оплата опаздывает. Запиши это в goal.problem через record_customer и не закрывай этап.");
        t.succeeded();
        t.calledTool("record_customer");
        t.notCalledTool("complete_stage");
      },
    },
  ],
});
