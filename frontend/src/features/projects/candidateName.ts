export function maskedCandidateName(value: string) {
  const name = value.trim()
  const characters = Array.from(name)
  if (characters.length <= 1) return name
  if (characters.length === 2) return `${characters[0]}*`
  return `${characters[0]}${'*'.repeat(characters.length - 2)}${characters.at(-1)}`
}
