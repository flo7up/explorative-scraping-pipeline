# Use Case Patterns

This repository is intentionally configurable. Change `pipeline.config.json` and prompt behavior to fit the domain you want to explore.

## Pattern 1: AIUseCaseHub-Style AI Use Case Discovery

AIUseCaseHub.com can be represented as a pipeline that discovers public enterprise AI deployment examples.

Useful configuration:

- `recordType`: `ai_use_case`
- `domainDescription`: public enterprise AI deployments, customer stories, partner case studies, and implementation examples
- `schema.fields`:
  - title
  - organization
  - summary
  - sourceUrl
  - industry
  - businessDomain
  - technologies
  - cloudProviders
  - partners
  - country
  - evidenceQuote
- `sourceDiscovery.seedUrls`:
  - customer story directories
  - partner case study pages
  - vendor blogs
  - public press release feeds
- `quality.requireSourceEvidence`: true
- `quality.reviewBeforeStore`: true

Start small. Use 3-5 seed URLs and `maxLinksPerSource` of 10-25 until the extraction quality is stable.

## Pattern 2: Vendor Ecosystem Case Studies

Track how a vendor ecosystem deploys products across customers and partners.

Useful fields:

- customer
- partner
- product
- industry
- geography
- business outcome
- quantified impact
- source evidence

## Pattern 3: Sustainability / ESG Project Discovery

Track public sustainability projects, climate technology deployments, or ESG reporting examples.

Useful fields:

- project name
- organization
- sustainability theme
- emission or resource metric
- geography
- technology used
- source evidence

## Pattern 4: Public Sector Digital Service Monitoring

Track modernization projects across agencies or municipalities.

Useful fields:

- agency
- jurisdiction
- service area
- citizen outcome
- technology vendor
- procurement or launch source

## Pattern 5: Competitor Launch Monitoring

Track public product launches and customer announcements.

Useful fields:

- company
- product
- launch type
- target market
- customer segment
- partner ecosystem
- source URL

## Pattern 6: Real Estate Project Discovery

Track public real estate projects across developer portfolios, planning portals, construction news, investment announcements, and municipality pages.

Useful fields:

- project name
- developer or owner
- asset class, such as residential, office, logistics, retail, hospitality, mixed-use, or infrastructure
- location, city, region, and country
- project status, such as proposed, approved, under construction, completed, or delayed
- expected completion date
- unit count, floor area, site area, or investment volume
- architect, contractor, operator, or key partners
- sustainability certifications or energy features
- planning reference, permit ID, or source authority
- source evidence

Useful seed sources:

- developer project pages
- city planning and building permit portals
- real estate investment trust updates
- construction and property news sites
- infrastructure authority project pages
- public consultation pages

Recommended quality gates:

- require a location and project name before storing
- require source evidence for status, size, or completion dates
- use duplicate checks for project names plus normalized location, because the same development often appears in several news sources
- keep review-before-store enabled when monitoring planning portals or news feeds with ambiguous project names

## Other Good Fits

The same pattern also works for:

- grants, tenders, and funding opportunities
- clinical trial or research program discovery from public registries
- supplier and partner ecosystem mapping
- policy, regulation, or compliance update monitoring
- conference session, speaker, and agenda extraction
- nonprofit program and impact story discovery

## Recommended Workflow For A New Domain

1. Copy `examples/aiusecasehub.pipeline.config.json` or another example.
2. Update `domainDescription` and schema fields.
3. Add 3-5 seed URLs.
4. Run `HttpScreenSources` manually.
5. Inspect candidates and extracted records.
6. Tighten `allowedDomains`, schema fields, and prompts.
7. Increase source count and revisit cadence only after quality is acceptable.
