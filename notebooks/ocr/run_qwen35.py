from openai import OpenAI
# Configured by environment variables
client = OpenAI()

messages = [
    {"role": "user", "content": "Type \"I love Qwen3.5\" backwards"},
]

chat_response = client.chat.completions.create(
    model="Qwen/Qwen3.5-35B-A3B",
    messages=messages,
    max_tokens=81920,
    temperature=1.0,
    top_p=0.95,
    presence_penalty=1.5,
    extra_body={
        "top_k": 20,
    }, 
)
print("Chat response:", chat_response)
