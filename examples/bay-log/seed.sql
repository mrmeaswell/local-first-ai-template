INSERT INTO users(name,role) VALUES ('Student A','student'),('Lead Instructor','lead');
INSERT INTO records(title,stage,owner,notes) VALUES
 ('2014 Honda Civic - squealing brakes','Diagnosis','Student A','Customer reports squeal at low speed.'||char(10)),
 ('2009 Ford F-150 - check engine light P0301','Diagnosis','Student B',''),
 ('2018 Toyota Camry - oil change + inspection','Repair','Student A','');
INSERT INTO kb(id,title,body) VALUES
 ('KB-001','Brake pad inspection','Measure pad thickness; replace below 3 mm. Inspect rotors for scoring. Check wear indicators.'),
 ('KB-002','Misfire diagnosis (P030x)','Swap coil to another cylinder, re-scan. If misfire follows coil, replace coil; else check plug and injector.'),
 ('KB-003','Oil change procedure','Verify spec in service manual, drain, replace filter, refill, reset maintenance light.');
