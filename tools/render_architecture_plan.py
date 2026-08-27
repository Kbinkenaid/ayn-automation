#!/usr/bin/env python3
"""Render the AYN Thor automation architecture plan as a polished PDF."""
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    KeepTogether,
    ListFlowable,
    ListItem,
    PageBreak,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "output" / "pdf" / "ayn-thor-automation-architecture-plan.pdf"

NAVY = colors.HexColor("#102A43")
BLUE = colors.HexColor("#1479B8")
TEAL = colors.HexColor("#137C8B")
MINT = colors.HexColor("#E6FFFA")
PALE_BLUE = colors.HexColor("#EAF4FB")
PALE_GREY = colors.HexColor("#F5F7FA")
SLATE = colors.HexColor("#486581")
RED = colors.HexColor("#B42318")

styles = getSampleStyleSheet()
styles.add(ParagraphStyle(
    name="CoverTitle", parent=styles["Title"], fontName="Helvetica-Bold",
    fontSize=30, leading=36, textColor=NAVY, alignment=TA_CENTER, spaceAfter=14,
))
styles.add(ParagraphStyle(
    name="CoverSub", parent=styles["Normal"], fontName="Helvetica", fontSize=13,
    leading=19, textColor=SLATE, alignment=TA_CENTER,
))
styles.add(ParagraphStyle(
    name="H1Plan", parent=styles["Heading1"], fontName="Helvetica-Bold",
    fontSize=18, leading=22, textColor=NAVY, spaceBefore=16, spaceAfter=9,
))
styles.add(ParagraphStyle(
    name="H2Plan", parent=styles["Heading2"], fontName="Helvetica-Bold",
    fontSize=13, leading=16, textColor=TEAL, spaceBefore=12, spaceAfter=6,
))
styles.add(ParagraphStyle(
    name="BodyPlan", parent=styles["BodyText"], fontName="Helvetica", fontSize=9.4,
    leading=13.4, textColor=colors.HexColor("#243B53"), spaceAfter=6,
))
styles.add(ParagraphStyle(
    name="SmallPlan", parent=styles["BodyText"], fontName="Helvetica", fontSize=8.1,
    leading=10.7, textColor=colors.HexColor("#334E68"),
))
styles.add(ParagraphStyle(
    name="TableHead", parent=styles["BodyText"], fontName="Helvetica-Bold", fontSize=7.7,
    leading=9.3, textColor=colors.white,
))
styles.add(ParagraphStyle(
    name="TableCell", parent=styles["BodyText"], fontName="Helvetica", fontSize=7.3,
    leading=9.1, textColor=colors.HexColor("#243B53"),
))
styles.add(ParagraphStyle(
    name="Callout", parent=styles["BodyText"], fontName="Helvetica-Bold", fontSize=9.5,
    leading=13.3, textColor=NAVY,
))


def p(text, style="BodyPlan"):
    return Paragraph(text, styles[style])


def bullet(items):
    return ListFlowable(
        [ListItem(p(item), leftIndent=8) for item in items],
        bulletType="bullet", leftIndent=18, bulletFontName="Helvetica", bulletFontSize=7,
        bulletColor=TEAL, spaceAfter=7,
    )


def table(headers, rows, widths):
    data = [[p(h, "TableHead") for h in headers]]
    for row in rows:
        data.append([p(cell, "TableCell") for cell in row])
    out = Table(data, colWidths=widths, repeatRows=1, hAlign="LEFT")
    out.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#CBD5E0")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, PALE_GREY]),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    return out


def phase(title, objective, implementation, references, verify, avoid):
    flows = [
        p(title, "H2Plan"),
        p("<b>Objective.</b> " + objective),
        p("<b>Implement.</b> " + implementation),
        p("<b>Reference current patterns.</b> " + references, "SmallPlan"),
        p("<b>Verify.</b> " + verify, "SmallPlan"),
        p("<b>Guardrails.</b> " + avoid, "SmallPlan"),
    ]
    return flows


def page_number(canvas, doc):
    canvas.saveState()
    canvas.setStrokeColor(colors.HexColor("#D9E2EC"))
    canvas.line(0.65 * inch, 0.54 * inch, 7.85 * inch, 0.54 * inch)
    canvas.setFont("Helvetica", 7.5)
    canvas.setFillColor(SLATE)
    canvas.drawString(0.65 * inch, 0.34 * inch, "AYN Thor automation architecture plan")
    canvas.drawRightString(7.85 * inch, 0.34 * inch, f"Page {doc.page}")
    canvas.restoreState()


def build():
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    doc = BaseDocTemplate(
        str(OUTPUT), pagesize=letter,
        leftMargin=0.65 * inch, rightMargin=0.65 * inch,
        topMargin=0.63 * inch, bottomMargin=0.72 * inch,
        title="AYN Thor Automation Architecture Plan",
        author="Codex",
    )
    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="main")
    doc.addPageTemplates([])
    from reportlab.platypus import PageTemplate
    doc.addPageTemplates([PageTemplate(id="all", frames=[frame], onPage=page_number)])

    story = []
    story += [Spacer(1, 1.25 * inch), p("AYN THOR", "CoverSub"), Spacer(1, 0.12 * inch)]
    story += [p("Automation Architecture Plan", "CoverTitle")]
    story += [p("A safe, deterministic, device-aware system for preparing a game library, enrolling one physical Thor, configuring supported emulators, and proving the result.", "CoverSub")]
    story += [Spacer(1, 0.38 * inch)]
    callout = Table([[p("Target definition: 100% orchestrated and auditable - not unsafe unattended clicking. Every permitted action is deterministic, hashed, resumable, and reported; permissions, personally supplied BIOS/keys/firmware, credentials, GPU-driver choice, and physical controls stay explicit human gates.", "Callout")]], colWidths=[6.65 * inch])
    callout.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), MINT),
        ("BOX", (0, 0), (-1, -1), 0.8, TEAL),
        ("LEFTPADDING", (0, 0), (-1, -1), 15),
        ("RIGHTPADDING", (0, 0), (-1, -1), 15),
        ("TOPPADDING", (0, 0), (-1, -1), 14),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 14),
    ]))
    story += [callout, Spacer(1, 0.42 * inch)]
    story += [p("Prepared from the existing ayn-automation project, its emulator profile, safety tests, and the local AYN Thor starter-guide transcript.", "CoverSub")]
    story += [Spacer(1, 2.0 * inch), p("Architecture scope: Mac preparation, library management, one explicitly selected AYN Thor, optional internal or removable ROM storage, emulator configuration, Cocoon frontend, acceptance, and recovery.", "SmallPlan")]
    story += [PageBreak()]

    story += [p("1. Executive architecture", "H1Plan")]
    story += [p("The project should become a local control plane named <b>thorctl</b>. It is the only component allowed to perform device actions. A conversational agent such as Hermes may guide the flow, but it calls thorctl endpoints and cannot bypass identity, approval, storage, or transfer checks.")]
    story += [p("The source of truth is a chain of signed or hashed records: canonical library manifest, device attestation, storage binding, app lock, deployment plan, run journal, acceptance report, and final redacted report.")]
    architecture_rows = [
        ["1. Content", "Owned game files and SSD library", "Canonical file manifest with platform, role, size and SHA-256"],
        ["2. Control plane", "thorctl JSON CLI", "Validates state transitions, approvals and allowed operations"],
        ["3. Device binding", "One explicit ADB serial", "Model, build fingerprint, package inventory, capabilities and timestamp"],
        ["4. Storage", "Internal or removable selection", "User-confirmed ROM root, free-space proof and write validation"],
        ["5. Deployment", "Pinned apps + manifest transfer", "Journaled copies, all-file verification and no implicit deletion"],
        ["6. App adapters", "Per-emulator compatibility modules", "Detect, render, apply safe changes, verify or issue manual gate"],
        ["7. Acceptance", "One title per platform", "Controls, saves, exit, dual-screen, renderer and frontend evidence"],
    ]
    story += [table(["Layer", "Input", "Output / responsibility"], architecture_rows, [0.72*inch, 2.0*inch, 3.93*inch])]
    story += [Spacer(1, 0.13 * inch)]
    story += [p("The key boundary: ROM management and planning can run today. Device enrollment, storage selection, app/version discovery, and actual adapter support begin only when the physical Thor is connected.", "Callout")]

    story += [p("2. Current capabilities and gaps", "H1Plan")]
    current_rows = [
        ["Library", "Canonical SSD manifest, dry-run sync, SHA-256, resumption, no implicit deletion", "Use as the only ROM-transfer input"],
        ["Intake", "Platform classifier and safe archive review", "Keep decisions immutable and review ambiguous disc images"],
        ["Profile", "Versioned AYN profile and non-authorizing plan", "Promote manual text into typed tasks"],
        ["Device", "Explicit-serial probe and ADB helper primitives", "Add identity attestation, consent and durable state"],
        ["Deployment", "Legacy deploy script intentionally disabled", "Build a new controller; do not reactivate it"],
        ["Apps", "Downloader resolves mutable releases", "Add app lock, signer checks and immutable provenance"],
        ["Recovery", "Golden capture/restore prototype", "Keep opt-in and redesign only after device acceptance"],
    ]
    story += [table(["Area", "What exists", "Required upgrade"], current_rows, [0.8*inch, 3.1*inch, 2.75*inch])]

    story += [p("3. Endpoint map", "H1Plan")]
    story += [p("Endpoints are local CLI subcommands with JSON input and output. They can later be wrapped by Hermes, a desktop UI, or a local HTTP service without changing their contracts.")]
    endpoint_rows = [
        ["library.scan / sync / verify", "Existing", "Canonical game manifest, staging plan, all-file local verification", "Scan is read-only; apply is explicit"],
        ["content.ingest", "Existing", "Safe classification and archive-member review", "No ambiguous format guessing"],
        ["profile.validate / plan", "Existing", "Validate profile and emit non-authorizing plan", "Never modifies a device"],
        ["device.discover", "New", "Verify named serial and capture full identity", "No first-device selection"],
        ["device.probe", "Extend", "Consent-based capability and storage checks", "No arbitrary app-data writes"],
        ["storage.bind", "New", "Confirm internal or removable ROM root", "User confirms Android picker result"],
        ["apps.lock / fetch / verify / inventory", "New", "APK provenance, signer and installed-version inventory", "No mutable latest APK trust"],
        ["deployment.plan / apply", "New", "Immutable intents, approval, journal and retry", "Approval bound to exact plan hash"],
        ["transfer.verify", "New", "Remote SHA-256 for every manifest file", "Replaces five-file sampling"],
        ["adapter.<emulator>", "New", "Detect, configure, read back, smoke-test or manual gate", "Version and signer gated"],
        ["acceptance.run", "New", "Per-platform technical + human acceptance", "Records evidence, not secrets"],
        ["frontend.commit / report.export", "New", "Cocoon activation and redacted final report", "Only accepted platforms become visible"],
    ]
    story += [table(["Endpoint", "Status", "Responsibility", "Gate"], endpoint_rows, [1.35*inch, 0.62*inch, 2.77*inch, 1.91*inch])]

    story += [p("4. Core records and authorization", "H1Plan")]
    story += [p("Every record is schema-versioned, atomically written, redacted, timestamped, and linked by digest. No record may contain BIOS contents, firmware, title keys, credentials, raw screenshots with private information, or app-private dumps.")]
    contract_rows = [
        ["DeviceAttestation", "serial, model, brand, Android build fingerprint, patch level, discovery time", "Expires if fingerprint changes"],
        ["StorageBinding", "internal/removable choice, selected ROM root, free space, confirmation", "Created after user selects storage"],
        ["AppLock", "source, release, SHA-256, package, signer, architecture, approved version", "Required before install"],
        ["DeploymentPlan", "library digest, profile, adapters, app lock, device, storage, ordered intents", "Pure plan; no device changes"],
        ["RunJournal", "intent statuses, retries, error codes, remote hashes and timestamps", "Supports resume and audit"],
        ["AcceptanceReport", "game/platform result, app version, renderer, user confirmations", "Required before frontend activation"],
    ]
    story += [table(["Record", "Minimum metadata", "Rule"], contract_rows, [1.25*inch, 3.8*inch, 1.6*inch])]
    story += [p("A deployment approval is valid only for: <b>device fingerprint + storage binding + library-manifest digest + profile/adapters + app-lock digest</b>. Any change invalidates the approval.", "Callout")]

    story += [p("5. State machine", "H1Plan")]
    story += [p("DRAFT (scan, classify, profile) -> DEVICE_ATTESTED -> STORAGE_BOUND -> PLAN_REVIEWED -> APPROVED -> MUTATING -> TRANSFER_VERIFIED -> PER_APP_ACCEPTED -> FRONTEND_ACCEPTED -> COMPLETE")]
    story += [p("Failure states: <b>BLOCKED</b> (precondition missing), <b>PARTIAL_RESUMABLE</b> (disconnect or interruption), and <b>ROLLBACK_REQUIRED</b> (a verified supported action needs recovery).")]
    story += [bullet([
        "The plan may report advisory readiness, but only an approval bound to the exact records authorizes apply.",
        "Every mutating intent re-checks device identity, storage binding, free space and applicable app compatibility immediately before execution.",
        "Unknown emulator state is a manual gate, not an automation failure hidden as success.",
    ])]

    story += [p("6. Implementation plan", "H1Plan")]
    story += phase(
        "Phase 0 - Repository hygiene and reproducibility",
        "Separate reusable automation source from games, APKs, personal artifacts and secrets before GitHub or continued development.",
        "Initialize a private repository; add a strict .gitignore/allowlist; retain scripts, profiles, tests and docs only. Exclude sd_card/ROMs, APKs, vendor ROM archives, BIOS/keys/firmware, audio cache, virtual environments, logs, reports and ~/.thor-provision.",
        "Follow existing project boundaries in README.md and the local state conventions in lib_thor.py.",
        "A clean clone runs the unit suite and contains no ROMs, APK binaries, secret-like files or 100 MB-plus artifacts.",
        "Do not use Git LFS as a ROM backup. Do not make the repository public while personally sourced assets remain in the tree.",
    )
    story += phase(
        "Phase 1 - thorctl control plane and schemas",
        "Create one local CLI/API contract that becomes the sole route to device mutation.",
        "Implement stdlib JSON schemas, stable run IDs, atomic records, lock ownership, exit codes and --dry-run support. Wrap existing thor_library, ingest_library, emulator_profiles and lib_thor primitives rather than duplicating them.",
        "Reuse lib_thor.Adb, Lock, logger_for, sha256_file and atomic_write; preserve emulator_profiles path containment.",
        "Mock-CLI tests prove invalid records, concurrent runs, expired approvals and malformed paths fail closed.",
        "Do not let Hermes, scripts or a UI call raw adb shell commands outside thorctl.",
    )
    story += phase(
        "Phase 2 - Device enrollment and storage binding",
        "Bind a plan to one physical Thor and one explicitly approved storage location.",
        "Implement device.discover with serial, full build fingerprint, model/brand/device metadata and installed package inventory. Implement storage.bind for user-selected internal/removable ROM root, free-space and write validation.",
        "Extend probe.py explicit-serial behavior and the first-device acceptance checklist; store data under ~/.thor-provision.",
        "Changed fingerprint, second device, root path escape, missing free space or failed write validation blocks the plan.",
        "Never assume /sdcard is a removable card. Never infer the first adb device. Never claim SAF permission solely because ADB can write.",
    )
    story += phase(
        "Phase 3 - Pinned APK supply chain",
        "Make every installed app reproducible and reviewable.",
        "Create app-lock.json and apps.lock/fetch/verify/inventory commands. Validate source release, host SHA-256, package ID, version code/name, signing certificate digest and ABI before installation; record runtime permission decisions separately.",
        "Replace mutable-release assumptions in apps.py with locked artifact records; use lib_thor install primitives only after lock verification.",
        "Wrong hash, signer, package, ABI, version or install result blocks the run and emits a diagnostic report.",
        "Do not trust filenames or a latest-release URL. Do not grant runtime permissions silently by default.",
    )
    story += phase(
        "Phase 4 - Manifest-driven transfer and verification",
        "Transfer exactly the reviewed game manifest, restart safely after interruption, and prove all remote content matches.",
        "Build device-side staging, transfer journals, streamed per-file hashes, remote hash verification, conflict detection and supported promotion. Preserve base/update/DLC roles and do not delete device content by default.",
        "Use thor_library canonical manifest and streamed sha256_file; replace lib_thor push_dir_verified sampling with a manifest verifier.",
        "Simulate disconnect, low space, corrupt remote file, existing conflict and resume. Verify every planned game hash, including large XCI files.",
        "Do not read whole ROMs into memory. Do not count a zero exit status as proof. Do not create ROMs/ROMs nesting.",
    )
    story += phase(
        "Phase 5 - Versioned emulator adapters",
        "Convert guide recommendations into capability-gated, testable per-app adapters.",
        "Define detect, compatibility, render_desired_state, apply_safe_changes, readback, manual_tasks, smoke_test and rollback for each emulator. Start with RetroArch, PPSSPP, Dolphin and DuckStation, then NetherSX2, Azahar, MelonDS, Cemu, Eden and Cocoon.",
        "Use profiles/ayn-thor-v1.json as the desired-state source and the first-device checklist as the human-gate source.",
        "Each adapter is tested against supported app versions and produces evidence or a clear manual task. Unsupported versions never apply writes.",
        "No generic UI macro. No fixed Android/data assumption. No automatic key/firmware/credential import or GPU driver choice.",
    )
    story += phase(
        "Phase 6 - Switch lifecycle and Cocoon frontend",
        "Treat base games, updates and DLC as related assets, and expose only valid base games in the frontend.",
        "Create a title relationship catalog with base title, update/DLC, title ID, hashes and acceptance state. Generate a Cocoon catalog only for accepted platforms; Smart Folders, mappings and Home assignment occur after launch tests.",
        "Follow Eden and Cocoon manual tasks in the profile. Maintain existing library role detection for base, update and DLC.",
        "Smash Ultimate appears once as a base game; DLC does not appear as 99 separate frontend entries. Failed launch blocks Cocoon mapping.",
        "Do not auto-install Switch DLC without owner/title-ID confirmation. Do not set Cocoon as Home before Back navigation passes.",
    )
    story += phase(
        "Phase 7 - Acceptance, recovery and release",
        "Prove the system works on the real hardware and make future recovery safe.",
        "Run one owned title per accepted platform. Record controls, save/load, exit, orientation/touch, renderer and Eden driver results. Redesign golden snapshot only after stable acceptance, with encrypted local storage and selective supported paths.",
        "Use the existing acceptance document as the baseline; keep golden.py isolated until its backup, restore and verification model is redesigned.",
        "Final report links every approved record and has no sensitive content. Restore tests are performed before restore is offered as a recovery action.",
        "Do not use golden restore as bootstrap. Do not snapshot arbitrary app-private data or secrets.",
    )

    story += [PageBreak(), p("7. Emulator adapter program", "H1Plan")]
    adapter_rows = [
        ["RetroArch", "Staged config import, BIOS folder, Vulkan, cores, hotkeys", "Manual import and core/version validation"],
        ["Azahar", "N3DS path, Vulkan, 4x, dual layout defaults", "SAF, user data, touch/stylus and hotkey verification"],
        ["MelonDS", "NDS path, OpenGL, 4x, dual layout defaults", "Folder access, touch, R2/R3/L3 checks"],
        ["Eden", "Switch ROM root and base/update/DLC catalog", "Keys, firmware, GPU driver, title ID and DLC management"],
        ["Dolphin / Cemu", "GC/Wii/Wii U paths and supported defaults", "SAF, per-game graphics/control/pad checks"],
        ["DuckStation / NetherSX2 / PPSSPP", "ROM and BIOS/data paths, documented defaults", "BIOS selection, controls, saves and per-game renderer validation"],
        ["Cocoon", "Base-game catalog and accepted mappings", "Storage picker, credentials, scraping, Home assignment"],
    ]
    story += [table(["Adapter", "Automatable when compatible", "Always approval-gated"], adapter_rows, [1.42*inch, 2.7*inch, 2.53*inch])]
    story += [p("The adapter rule: if package signer, app version, storage schema or config format is unrecognized, stop at a typed manual task. A truthful manual task is better than a false automated success.", "Callout")]

    story += [p("8. Test and release strategy", "H1Plan")]
    test_rows = [
        ["Unit", "Schemas, path containment, role classification, hashing, redaction, state transitions", "Runs on Mac for every change"],
        ["Mock ADB", "Identity mismatch, remote path quoting, install failure, low space, transfer retry, rollback", "No physical device required"],
        ["Android emulator", "Basic package inventory and shared storage behavior", "Useful but not a Thor substitute"],
        ["Physical Thor", "SAF, dual screens, controls, GPU driver, emulator versions and frontend behavior", "Required before support claim"],
        ["Acceptance regression", "One owned title per emulator/platform after app or profile changes", "Evidence updates the compatibility matrix"],
    ]
    story += [table(["Layer", "Coverage", "When"], test_rows, [1.2*inch, 3.9*inch, 1.55*inch])]
    story += [bullet([
        "CI must run the existing tests plus new mock-ADB contracts, secret scans and dependency checks.",
        "A device adapter is supported only after exact app-version, signer and physical-Thor acceptance evidence exists.",
        "Every release emits a compatibility matrix rather than a vague claim that all Thor devices work.",
    ])]

    story += [p("9. Security and operational rules", "H1Plan")]
    story += [bullet([
        "No first connected-device selection. Every mutation includes adb -s with an attested serial.",
        "No hardcoded internal or removable storage paths. A user-approved storage binding is mandatory.",
        "No unpinned APK downloads, no unverified signer, and no ignored installation error.",
        "No BIOS, firmware, title keys, passwords, API keys or credentials in source control, reports, logs or agent memory.",
        "No destructive delete or replace of canonical SSD/device content without a reviewed recovery action.",
        "No archive extraction or ambiguous .iso/.rvz/.bin routing without the existing safe review flow.",
        "No success status until all-file transfer verification and acceptance evidence pass.",
    ])]

    story += [p("10. Final operating flow", "H1Plan")]
    flow_rows = [
        ["1", "Prepare", "Scan library, resolve classification reviews, validate profile, lock apps"],
        ["2", "Connect", "Enable debugging, name exact serial, discover identity, run consented probe"],
        ["3", "Bind", "Choose internal or removable ROM root through Android, validate space/access"],
        ["4", "Review", "Generate immutable deployment plan and inspect actions, risks and manual gates"],
        ["5", "Approve", "Approve the exact plan hash for the exact device and storage binding"],
        ["6", "Apply", "Install verified apps and transfer reviewed content with journal/resume/hash checks"],
        ["7", "Configure", "Run supported adapters; complete typed on-device permissions and secret gates"],
        ["8", "Accept", "Test one owned game/platform; record results; enable Cocoon only for passes"],
        ["9", "Report", "Export redacted report and optional validated recovery snapshot"],
    ]
    story += [table(["Step", "Stage", "Outcome"], flow_rows, [0.45*inch, 1.0*inch, 5.2*inch])]
    story += [Spacer(1, 0.18*inch), p("Recommended next implementation move: complete Phase 0 and Phase 1 before the physical Thor arrives. Once it is connected, build Phase 2 through Phase 5 against its real app versions and storage behavior.", "Callout")]
    story += [Spacer(1, 0.16*inch), p("Source basis: current local repository components including thor_library.py, ingest_library.py, lib_thor.py, probe.py, emulator_profiles.py, profiles/ayn-thor-v1.json, README.md, and docs/AYN-THOR-FIRST-DEVICE-ACCEPTANCE.md.", "SmallPlan")]

    doc.build(story)
    print(OUTPUT)


if __name__ == "__main__":
    build()
