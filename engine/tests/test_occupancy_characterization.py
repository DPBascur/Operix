"""Fixtures adversariales de ocupancia; señales diagnósticas, nunca un clasificador."""
import unittest

from operix_engine.detection import BoundingBox
from operix_engine.proximity_geometry import nearest_ground_edges


FORK = (200,200,600,500)
CAB = (420,220,540,390)  # Anotación de este fixture, no ROI universal del producto.
CASES = {
    "obvious_occupant": (445,235,500,375),
    "front_pedestrian_projected": (445,235,500,375),
    "side_pedestrian": (560,280,660,500),
    "behind_pedestrian_projected": (445,235,500,375),
    "partially_visible_occupant": (470,250,510,330),
    "second_person": (380,320,440,500),
}


def containment(person, equipment):
    intersection = max(0,min(person[2],equipment[2])-max(person[0],equipment[0])) * max(
        0,min(person[3],equipment[3])-max(person[1],equipment[1]))
    return intersection / ((person[2]-person[0])*(person[3]-person[1]))


def signals(person, equipment=FORK, cab=CAB):
    measured = nearest_ground_edges(BoundingBox(*person),BoundingBox(*equipment),1000,600)
    return {"containment":containment(person,equipment),
            "fixture_cab_containment":containment(person,cab),
            "relative_center_x":((person[0]+person[2])/2-equipment[0])/(equipment[2]-equipment[0]),
            "relative_bottom_y":(person[3]-equipment[1])/(equipment[3]-equipment[1]),
            "ground_edge_distance":measured.normalized_distance}


def translated(box, dx, dy):
    return (box[0]+dx,box[1]+dy,box[2]+dx,box[3]+dy)


class OccupancyCharacterizationTests(unittest.TestCase):
    def test_cab_containment_does_not_disambiguate_projected_pedestrian(self):
        occupant = signals(CASES["obvious_occupant"])
        self.assertEqual(occupant["containment"],1.)
        self.assertEqual(occupant["fixture_cab_containment"],1.)
        for name in ("front_pedestrian_projected","behind_pedestrian_projected"):
            # Roles físicos diferentes del fixture, observaciones 2D idénticas.
            self.assertEqual(occupant,signals(CASES[name]))

    def test_side_pedestrian_can_overlap_and_have_zero_ground_distance(self):
        observed = signals(CASES["side_pedestrian"])
        self.assertGreater(observed["containment"],0.)
        self.assertLess(observed["containment"],1.)
        self.assertEqual(observed["ground_edge_distance"],0.)

    def test_partially_visible_occupant_has_no_full_body_or_role_evidence(self):
        observed = signals(CASES["partially_visible_occupant"])
        self.assertEqual(observed["containment"],1.)
        self.assertEqual(observed["fixture_cab_containment"],1.)
        self.assertGreater(observed["ground_edge_distance"],0.)

    def test_static_equipment_cannot_use_absence_of_motion_as_role_evidence(self):
        # Todos los desplazamientos/velocidades relativos son cero en ambos casos.
        one = [signals(CASES["obvious_occupant"]) for _ in range(6)]
        other = [signals(CASES["front_pedestrian_projected"]) for _ in range(6)]
        self.assertEqual(one,other)

    def test_correlated_motion_and_persistence_still_allow_pedestrian_counterexample(self):
        sequences = []
        for name in ("obvious_occupant","front_pedestrian_projected"):
            sequences.append([signals(translated(CASES[name],2*i,i),translated(FORK,2*i,i),
                                      translated(CAB,2*i,i)) for i in range(6)])
        self.assertEqual(sequences[0],sequences[1])
        # Mismo vector (2,1), dirección y velocidad relativa cero. No decide rol.
        for sample in sequences[0]:
            for name,value in sample.items():
                self.assertAlmostEqual(value,sequences[0][0][name])

    def test_two_people_operator_and_pedestrian_keep_independent_observations(self):
        people = (CASES["obvious_occupant"],CASES["second_person"])
        observed = [signals(person) for person in people]
        self.assertEqual(len(observed),2)
        self.assertNotEqual(observed[0],observed[1])
        self.assertEqual(observed[1]["ground_edge_distance"],0.)

    def test_person_near_other_equipment_is_not_removed_by_containment_in_first(self):
        person = CASES["obvious_occupant"]
        other = (530,220,850,500)
        first, second = signals(person), signals(person,other)
        self.assertEqual(first["containment"],1.)
        self.assertEqual(second["containment"],0.)
        self.assertGreater(second["ground_edge_distance"],first["ground_edge_distance"])
        self.assertEqual(person,CASES["obvious_occupant"])

    def test_fragmented_identity_cannot_inherit_a_confirmed_physical_role(self):
        # Las señales geométricas no contienen prueba de identidad entre IDs.
        histories = []
        for name in ("obvious_occupant","front_pedestrian_projected"):
            histories.append([(1,0.,signals(CASES[name])),(None,.1,None),(2,.2,signals(CASES[name]))])
        self.assertEqual(histories[0],histories[1])


if __name__ == "__main__":
    unittest.main()
