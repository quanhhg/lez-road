[out:json][timeout:180][date:"2026-10-01T00:00:00Z"];
way["highway"](20.615765,105.865644,20.661190,105.913900)->.roads;
rel(bw.roads)["type"="restriction"]->.turns;
(
  .roads;
  .turns;
  node["highway"="traffic_signals"](20.615765,105.865644,20.661190,105.913900);
  node["barrier"](20.615765,105.865644,20.661190,105.913900);
);
(._; >>;);
out meta;
out count;
