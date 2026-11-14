# saves conversation history and system prompt, builds messages for llm input
class ConversationManager:
    # constructor with maax_messages to keep and system_prompt for llm context
    def __init__(self, max_messages: int, system_prompt: str):
        self.system_prompt = system_prompt.strip()
        self.max_messages = max_messages
        # history as list of ditcs with role and content
        self.history: list[dict] = []

        # example history:
        # [
        #     {"role": "user", "content": "..."},
        #     {"role": "assistant", "content": "..."},
        #     {"role": "user", "content": "..."}
        # ]

    # add user message to history
    def add_user(self, text: str):
        self.history.append({"role": "user", "content": text})

    # add assistant message to history
    def add_assistant(self, text: str):
        self.history.append({"role": "assistant", "content": text})

    # keep only the most recent max_messages user+assistant pairs in history
    def trim(self):
        max_total = 2 * self.max_messages
        if len(self.history) > max_total:
            # keep only the last max_total messages
            self.history[:] = self.history[-max_total:]

    # builds full input for llm with system prompt and trimmed history
    def get_messages(self) -> list[dict]:
        # starts with system prompt, then add trimmed history
        return [{"role": "system", "content": self.system_prompt}, *self.history]
