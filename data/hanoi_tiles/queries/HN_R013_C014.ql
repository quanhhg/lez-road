[out:json][timeout:180][date:"2026-10-01T00:00:00Z"];
way["highway"](21.112405,105.916635,21.157847,105.965070)->.roads;
rel(bw.roads)["type"="restriction"]->.turns;
(
  .roads;
  .turns;
  node["highway"="traffic_signals"](21.112405,105.916635,21.157847,105.965070);
  node["barrier"](21.112405,105.916635,21.157847,105.965070);
);
(._; >>;);
out meta;
out count;
