type DialogueMessage = {
  speaker: string
  text: string
  side: 'left' | 'right'
}

const dialogueLinePattern = /^(用户([1-9][0-9]*))[：:]\s*(.*)$/

function parseDialogue(transcript: string): DialogueMessage[] {
  return transcript
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => {
      const match = line.match(dialogueLinePattern)
      if (!match) return { speaker: '转写', text: line, side: 'left' }

      return {
        speaker: match[1],
        text: match[3],
        side: Number(match[2]) % 2 === 0 ? 'right' : 'left',
      }
    })
}

export function DialogueTranscript({ transcript }: { transcript: string }) {
  const dialogue = parseDialogue(transcript)

  return (
    <section className="border-4 border-border bg-background p-5 shadow-[5px_5px_0_0_var(--border)] sm:p-6">
      <h2 className="font-head text-2xl">转写文本</h2>
      <div data-slot="dialogue-transcript" className="mt-6 flex flex-col gap-5">
        {dialogue.map((message, index) => (
          <article
            key={`${message.speaker}-${index}`}
            data-slot="dialogue-message"
            data-side={message.side}
            className={`flex w-full max-w-[92%] flex-col sm:max-w-[78%] ${
              message.side === 'right' ? 'self-end items-end' : 'self-start items-start'
            }`}
          >
            <p className="mb-2 px-2 font-head text-sm">{message.speaker}</p>
            <div
              className={`w-full border-[3px] border-border p-4 text-base leading-8 shadow-[5px_5px_0_0_var(--border)] ${
                message.side === 'right'
                  ? 'bg-green-200 shadow-[-5px_5px_0_0_var(--border)]'
                  : 'bg-background'
              }`}
            >
              <p className="whitespace-pre-wrap break-words">{message.text}</p>
            </div>
          </article>
        ))}
      </div>
    </section>
  )
}
