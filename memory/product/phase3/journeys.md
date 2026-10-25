# Phase 3 Journeys

Start each one after Reset demo. 1440×900. Earlier journeys remain valid except JRN-23 (superseded).

- **JRN-44** Fleet overview (supersedes JRN-23). Steps: click Fleet in the nav. Expected: tab pills show Carriers 1, Trucks 4, Drivers 4, Commitments 4. The Trucks table lists 101–104 with driver, location, status and availability. superseded: [JRN-23]
- **JRN-45** Edit truck cost. Steps: open Truck 101, change $/mi from 1.80 to 2.00, then Save. Expected: a "Saved" toast appears, and the dashboard After trip costs card goes down (Truck 101's segments are recalculated at $2.00). Reset restores $1,054.
- **JRN-46** Separate availability. Steps: open Truck 101 and Ava Reed. Expected: the truck shows release Mon 12:00 and the driver shows available Tue 07:00, as separate editable fields.
- **JRN-47** Validation. Steps: clear a driver's name; set a commitment's delivery window end before its start. Expected: inline errors appear and Save is disabled.
- **JRN-48** Edit commitment window. Steps: change L-103 pickup to Wed 09:00–10:00 and Save. Expected: the schedule block and the Truck 101 panel show 09:00–10:00.
- **JRN-49** Conversational intake. Steps: click Add, then type "Add truck 105, 53' dry van, in Fresno, available Tue 06:00, driver Maria Lopez 555-0142". Expected:
  - The confirmation card shows unit 105, equipment, location Fresno, availability, driver name and phone.
  - Confirm & save adds Truck 105 to the Trucks table, the dashboard strip and the map near Fresno.
  - The header shows "5 trucks".
- **JRN-50** Missing info. Steps: type "Add truck 106 in Stockton". Expected: Driver and availability are flagged "Needs info", and Confirm stays disabled until they are filled.
- **JRN-51** Duplicate. Steps: type "Add truck 101 ...". Expected: a warning "Truck 101 already exists" offers to edit the existing truck instead, and no duplicate is created.
- **JRN-52** Voice intake. Steps: click the mic in intake. Expected: a waveform appears, then the preset description is transcribed, then the confirmation card.
- **JRN-53** Carrier preferences. Steps: open Demo West Freight and set max deadhead to 50 mi. Expected: it saves and an activity entry is logged.
- **JRN-54** AI settings. Steps: open AI settings, set the negotiation floor to $2.50/mi, and toggle a Phase 2 rule off. Expected: the values persist, an activity entry is logged, the rule shows as inactive, and "Require approval before booking" is locked on.
- **JRN-55** Reset. Steps: after JRN-45, JRN-49 and JRN-54, Reset demo. Expected: 4 trucks, $1.80, the default settings and no Truck 105.
