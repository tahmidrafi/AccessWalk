/** The three steps behind a report, as an ordered list (icons are decorative). */
const STEPS = [
  {
    title: 'Film the walk',
    text: 'Phone upright, steady pace, from the bus stop or parking to the door. Faces are blurred and location data removed before any frame is analysed.',
    icon: (
      <>
        <rect x="14" y="4" width="20" height="40" rx="4" />
        <circle cx="24" cy="38" r="2" />
        <path d="M19 18 l10 6 -10 6 z" />
      </>
    ),
  },
  {
    title: 'SAM 3.1 tracks every object',
    text: "Meta's SAM 3.1 follows each step, curb, pole, bin and handrail across the frames, so every object keeps one identity along the route.",
    icon: (
      <>
        <rect x="5" y="10" width="18" height="18" />
        <rect x="25" y="20" width="18" height="18" strokeDasharray="4 3" />
        <path d="M14 34 v6 h20" />
      </>
    ),
  },
  {
    title: 'Review agent confirms each barrier with proof',
    text: 'An agent checks each likely barrier against its tracked object and cites the frame. What it cannot confirm is marked possible, to verify on site.',
    icon: (
      <>
        <rect x="6" y="6" width="36" height="28" rx="2" />
        <path d="M15 20 l6 6 12 -12" />
        <path d="M18 42 h12" />
      </>
    ),
  },
]

export function HowItWorks() {
  return (
    <section className="how" aria-labelledby="how-heading">
      <h2 id="how-heading">How it works</h2>
      <ol className="how-steps">
        {STEPS.map((s, i) => (
          <li key={s.title} className="how-step">
            <svg viewBox="0 0 48 48" className="how-icon" aria-hidden="true" focusable="false">
              {s.icon}
            </svg>
            <p className="how-n" aria-hidden="true">
              {i + 1}
            </p>
            <h3>{s.title}</h3>
            <p>{s.text}</p>
          </li>
        ))}
      </ol>
    </section>
  )
}
